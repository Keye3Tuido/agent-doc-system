#!/usr/bin/env python3
"""
doc-lint-consistency.py - Cross-reference consistency lint for the doc-system itself.

Usage: python3 ~/.agent-docs/scripts/doc-lint-consistency.py [package_root]

The manual, the SKILL.md files and the scripts each restate the same facts
(section numbers, script names, CLI flags, status codes, schema fields, paths).
Nothing kept those restatements in sync, so they drifted. This lint checks the
*referential* layer: every name/number/path/flag mentioned in prose must resolve
to something that actually exists.

Scope and limits: this catches broken and drifted references. It does NOT catch
semantic contradictions -- two prose passages that both parse fine but state
opposite rules. Making those structurally impossible needs a single machine
readable spec that the manual is generated from (phase 2).

Checks:
  MANUAL_SECTION_REF     a section number cited in prose has no such heading
  SCRIPT_REF             a script named in prose does not exist
  SCRIPT_FLAG_REF        a CLI flag shown for a script is not accepted by it
  UNKNOWN_FLAG           a flag in prose is declared by no script at all
  STATUS_CODE_REF        an ALL_CAPS status code in prose appears in no script
  SCHEMA_FIELD_SYNC      manual field table disagrees with doc-format-check.py
  HOME_PATH_REF          a ~/... path is never created by the installer
  SKILL_REGISTRY_SYNC    manual skill table, skills/ dirs and frontmatter differ
  SKILL_NUMBERING        step numbers inside a SKILL.md duplicate or skip
  SCHEMA_VERSION_SYNC    a hardcoded schema version disagrees with the manual
  FORBIDDEN_PHRASE       a wording the manual bans for contradicting real behaviour
  SCRIPT_REGISTRY_SYNC   a script exists but the manual's script table omits it
  TEMPLATE_REF           a template file named in prose does not exist

Output: one finding per line, or "ALL_PASS". Exit 1 if any finding.
"""

import os
import re
import sys

# ~/... prefixes that genuinely exist after install-global.py runs, plus the IDE
# skill directories the install docs legitimately reference.
KNOWN_HOME_PREFIXES = (
    "~/.agent-docs",
    "~/.agent/skills",
    "~/.claude",
    "~/.kiro",
    "~/.cursor",
    "~/.copilot",
    "~/.deepseek",
)

# The test harness ships with the package and is registered in the manual, but its
# fixtures deliberately embed outdated schema versions in order to verify that
# OUTDATED_SCHEMA_VERSION detection works. Exempt it from version-sync only.
SCHEMA_VERSION_EXEMPT = {"selftest.py"}
# Test fixtures quote expected status codes. They are evidence that a check is
# tested, not evidence that a production script still emits that status.
STATUS_SOURCE_EXEMPT = {"selftest.py"}

# Tokens that look like status codes but are prose or field values, not codes.
STATUS_CODE_IGNORE = {
    "UTF", "BOM", "CRLF", "LF", "CJK", "URL", "SHA", "YAML", "JSON", "IDE",
    "CLI", "API", "OK", "TODO", "MD", "PY", "SKILL", "README", "MMKV",
}


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class Lint:
    def __init__(self, root):
        self.root = root
        self.findings = []
        self.manual_path = os.path.join(root, "manual", "doc-system.md")
        self.scripts_dir = os.path.join(root, "scripts")
        self.skills_dir = os.path.join(root, "skills")
        self.templates_dir = os.path.join(root, "templates")
        self.manual = read(self.manual_path) if os.path.isfile(self.manual_path) else ""
        self.skills = {}
        if os.path.isdir(self.skills_dir):
            for name in sorted(os.listdir(self.skills_dir)):
                p = os.path.join(self.skills_dir, name, "SKILL.md")
                if os.path.isfile(p):
                    self.skills[name] = read(p)
        self.script_names = set()
        if os.path.isdir(self.scripts_dir):
            self.script_names = {
                n for n in os.listdir(self.scripts_dir)
                if n.endswith((".py", ".sh"))
            }

    def add(self, code, where, detail):
        self.findings.append(f"{where}: {code} {detail}")

    # -- prose corpus -----------------------------------------------------
    def corpus(self):
        """(label, text) for every prose file this lint governs."""
        out = []
        if self.manual:
            out.append(("manual/doc-system.md", self.manual))
        for name, text in self.skills.items():
            out.append((f"skills/{name}/SKILL.md", text))
        return out

    # -- 1. manual section references -------------------------------------
    def check_section_refs(self):
        headings = set()
        for m in re.finditer(r"^#{2,3}\s+(\d+(?:\.\d+)?)[.．]?\s", self.manual, re.M):
            headings.add(m.group(1))
        # "## 9. yaml ..." also satisfies a citation of plain "9"
        tops = {h.split(".")[0] for h in headings}
        for label, text in self.corpus():
            for m in re.finditer(r"§\s*(\d+(?:\.\d+)?)", text):
                ref = m.group(1)
                if ref in headings or ref in tops:
                    continue
                self.add("MANUAL_SECTION_REF", label, f"§{ref} 无对应章节标题")

    # -- 2. script references ---------------------------------------------
    def check_script_refs(self):
        for label, text in self.corpus():
            for m in re.finditer(r"([A-Za-z0-9_-]+\.(?:py|sh))", text):
                name = m.group(1)
                # only judge names that look like this project's tooling
                if not (name.startswith("doc-") or name in ("selftest.py",
                                                            "convert-to-utf8.sh",
                                                            "install-global.py")):
                    continue
                if name == "install-global.py":
                    if not os.path.isfile(os.path.join(self.root, "installers", name)):
                        self.add("SCRIPT_REF", label, f"{name} 不存在")
                    continue
                if name not in self.script_names:
                    self.add("SCRIPT_REF", label, f"{name} 不存在于 scripts/")

    # -- 3. CLI flags -----------------------------------------------------
    def declared_flags(self, script):
        path = os.path.join(self.scripts_dir, script)
        if not os.path.isfile(path):
            return None
        src = read(path)
        flags = set(re.findall(r'add_argument\(\s*"(--[a-z][a-z0-9-]*)"', src))
        # bash scripts declare flags in case patterns / --flag=* forms
        flags |= set(re.findall(r'(--[a-z][a-z0-9-]*)\)', src))
        flags |= set(re.findall(r'(--[a-z][a-z0-9-]*)=\*', src))
        return flags

    def check_script_flags(self):
        """Only judge flags inside a backticked command span that names exactly
        one script. Prose like "脚本 `--out` 输出" refers to no specific script,
        so judging every flag on the same line produces false positives."""
        cache = {}
        for label, text in self.corpus():
            for span in re.findall(r"`([^`]+)`", text):
                scripts = [s for s in re.findall(r"([A-Za-z0-9_-]+\.(?:py|sh))", span)
                           if s in self.script_names]
                if len(set(scripts)) != 1:
                    continue  # ambiguous or none: skip rather than guess
                script = scripts[0]
                if script not in cache:
                    cache[script] = self.declared_flags(script)
                declared = cache[script]
                if declared is None:
                    continue
                tail = span[span.index(script) + len(script):]
                for flag in re.findall(r"(?<![-\w])(--[a-z][a-z0-9-]*)", tail):
                    if flag not in declared:
                        self.add("SCRIPT_FLAG_REF", label,
                                 f"{script} 不接受 {flag}")

        # Weaker but safe companion check: a flag that no script anywhere declares
        # is a stale reference regardless of which script the prose meant.
        universe = set()
        for n in sorted(self.script_names):
            universe |= self.declared_flags(n) or set()
        for label, text in self.corpus():
            seen = set()
            for span in re.findall(r"`([^`]+)`", text):
                for flag in re.findall(r"(?<![-\w])(--[a-z][a-z0-9-]*)", span):
                    if flag in universe or flag in seen:
                        continue
                    seen.add(flag)
                    self.add("UNKNOWN_FLAG", label,
                             f"{flag} 未被任何脚本声明")

    # -- 4. status codes ---------------------------------------------------
    def check_status_codes(self):
        src_all = ""
        for n in sorted(self.script_names - STATUS_SOURCE_EXEMPT):
            src_all += read(os.path.join(self.scripts_dir, n))
        for label, text in self.corpus():
            seen = set()
            for m in re.finditer(r"`([A-Z][A-Z0-9_]{2,})`", text):
                code = m.group(1)
                if code in STATUS_CODE_IGNORE or code in seen:
                    continue
                seen.add(code)
                if code not in src_all:
                    self.add("STATUS_CODE_REF", label,
                             f"状态码 {code} 未出现在任何脚本中")

    # -- 5. schema field table vs doc-format-check.py ----------------------
    def check_schema_sync(self):
        fc_path = os.path.join(self.scripts_dir, "doc-format-check.py")
        if not os.path.isfile(fc_path) or not self.manual:
            return
        src = read(fc_path)

        def pylist(name):
            m = re.search(name + r"\s*=\s*\[(.*?)\]", src, re.S)
            return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()

        required_code = pylist("REQUIRED_FIELDS")
        allowed_code = pylist("ALLOWED_FIELDS")
        deprecated_code = pylist("DEPRECATED_FIELDS")

        # manual section 9 field table: | `field` | 是/否 | ... |
        sec = re.search(r"^##\s+9\..*?(?=^##\s+\d+\.)", self.manual, re.S | re.M)
        if not sec:
            self.add("SCHEMA_FIELD_SYNC", "manual/doc-system.md", "找不到 §9 章节")
            return
        body = sec.group(0)
        required_doc, listed_doc = set(), set()
        for m in re.finditer(r"^\|\s*`([a-z_.]+)`\s*\|\s*(是|否)\s*\|", body, re.M):
            field, req = m.group(1), m.group(2)
            top = field.split(".")[0]
            listed_doc.add(top)
            if req == "是":
                required_doc.add(top)

        for f in sorted(required_doc - required_code):
            self.add("SCHEMA_FIELD_SYNC", "manual/doc-system.md",
                     f"§9 标 `{f}` 必填，但 REQUIRED_FIELDS 中没有")
        for f in sorted(required_code - required_doc):
            self.add("SCHEMA_FIELD_SYNC", "scripts/doc-format-check.py",
                     f"REQUIRED_FIELDS 含 `{f}`，但 §9 未标为必填")
        for f in sorted(listed_doc - allowed_code):
            self.add("SCHEMA_FIELD_SYNC", "scripts/doc-format-check.py",
                     f"§9 允许字段含 `{f}`，但 ALLOWED_FIELDS 中没有")
        for f in sorted(allowed_code - listed_doc):
            self.add("SCHEMA_FIELD_SYNC", "manual/doc-system.md",
                     f"ALLOWED_FIELDS 含 `{f}`，但 §9 字段表未列出")

        # removal table: | `a` / `b` | reason | replacement |
        removed_doc = set()
        for m in re.finditer(r"^\|\s*((?:`[a-z_]+`\s*/?\s*)+)\|", body, re.M):
            removed_doc |= set(re.findall(r"`([a-z_]+)`", m.group(1)))
        removed_doc -= listed_doc
        for f in sorted(deprecated_code - removed_doc):
            self.add("SCHEMA_FIELD_SYNC", "manual/doc-system.md",
                     f"DEPRECATED_FIELDS 含 `{f}`，但 §9 移除表未列出")
        for f in sorted(removed_doc - deprecated_code):
            self.add("SCHEMA_FIELD_SYNC", "scripts/doc-format-check.py",
                     f"§9 移除表列出 `{f}`，但 DEPRECATED_FIELDS 中没有")

    # -- 6. home paths -----------------------------------------------------
    def check_home_paths(self):
        for label, text in self.corpus():
            seen = set()
            for m in re.finditer(r"~/[A-Za-z0-9._/-]+", text):
                path = m.group(0).rstrip("/.,;:)`")
                if path in seen:
                    continue
                seen.add(path)
                # Prefix match must respect path boundaries: "~/.agent-docs-venv"
                # is NOT under "~/.agent-docs".
                if not any(path == p or path.startswith(p + "/")
                           for p in KNOWN_HOME_PREFIXES):
                    self.add("HOME_PATH_REF", label,
                             f"{path} 不由安装器创建，也不属已知 IDE 目录")

    # -- 7. skill registry -------------------------------------------------
    def check_skill_registry(self):
        if not self.manual:
            return
        sec = re.search(r"^##\s+15\..*?(?=^##\s+16\.)", self.manual, re.S | re.M)
        listed = set()
        if sec:
            listed = {m.group(1) for m in
                      re.finditer(r"^\|\s*`/(doc-[a-z-]+)`", sec.group(0), re.M)}
        actual = set(self.skills)
        for name in sorted(listed - actual):
            self.add("SKILL_REGISTRY_SYNC", "manual/doc-system.md",
                     f"§15 列出 /{name}，但 skills/{name}/SKILL.md 不存在")
        for name in sorted(actual - listed):
            self.add("SKILL_REGISTRY_SYNC", "manual/doc-system.md",
                     f"skills/{name} 存在，但 §15 未登记")
        for name, text in self.skills.items():
            m = re.search(r"^name:\s*(\S+)", text, re.M)
            if not m:
                self.add("SKILL_REGISTRY_SYNC", f"skills/{name}/SKILL.md",
                         "frontmatter 缺少 name 字段")
            elif m.group(1) != name:
                self.add("SKILL_REGISTRY_SYNC", f"skills/{name}/SKILL.md",
                         f"frontmatter name={m.group(1)} 与目录名 {name} 不一致")

    # -- 8. numbering ------------------------------------------------------
    def check_skill_numbering(self):
        """Numbering restarts at every heading, so each section is its own
        sequence. Checking the whole file as one list would flag every skill
        that legitimately splits steps into 阶段 A / B / C."""
        for name, text in self.skills.items():
            label = f"skills/{name}/SKILL.md"
            in_fence = False
            section = "（开头）"
            tops, subs = [], []

            def flush(sec):
                self._seq(label, f"[{sec}] 步骤", [str(t) for t in tops])
                for i, group in enumerate(subs):
                    if group:
                        self._seq(label, f"[{sec}] 步骤 {tops[i]} 的子项", group)
                tops.clear()
                subs.clear()

            for line in text.split("\n"):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                m = re.match(r"^#{2,4}\s+(.*)", line)
                if m:
                    flush(section)
                    section = m.group(1).strip()
                    continue
                m = re.match(r"^(\d+)\.\s", line)
                if m:
                    tops.append(int(m.group(1)))
                    subs.append([])
                    continue
                m = re.match(r"^\s{2,4}([a-z])\.\s", line)
                if m and subs:
                    subs[-1].append(m.group(1))
            flush(section)

    def _seq(self, label, what, items):
        dups = {x for x in items if items.count(x) > 1}
        for d in sorted(dups):
            self.add("SKILL_NUMBERING", label, f"{what}编号 {d}. 重复")
        uniq = [x for i, x in enumerate(items) if x not in items[:i]]
        if not uniq:
            return
        expected = ([str(i) for i in range(1, len(uniq) + 1)]
                    if uniq[0].isdigit()
                    else [chr(ord("a") + i) for i in range(len(uniq))])
        if uniq != expected:
            self.add("SKILL_NUMBERING", label,
                     f"{what}编号不连续: {','.join(uniq)} (应为 {','.join(expected)})")

    # -- 9. hardcoded schema versions must match the manual ----------------
    def check_schema_version_sync(self):
        """The manual's yaml head is the single source of truth for the schema
        version. Anything that hardcodes a version must agree with it.

        This is not hypothetical: after the manual went to v7, templates/ and
        doc-scaffold.py still emitted v6, so every newly created document was
        born already flagged as OUTDATED_SCHEMA_VERSION.
        """
        m = re.search(r"^schema_version:\s*(\S+)", self.manual, re.M)
        if not m:
            self.add("SCHEMA_VERSION_SYNC", "manual/doc-system.md",
                     "yaml \u5934\u7f3a schema_version")
            return
        want = m.group(1)

        for rel in ("templates/_index.md", "templates/main-module.md"):
            p = os.path.join(self.root, rel)
            if not os.path.isfile(p):
                continue
            t = re.search(r"^schema_version:\s*(\S+)", read(p), re.M)
            if t and t.group(1) != want:
                self.add("SCHEMA_VERSION_SYNC", rel,
                         f"\u6a21\u677f\u5199 {t.group(1)}\uff0c\u624b\u518c\u662f {want}")

        fc = os.path.join(self.scripts_dir, "doc-format-check.py")
        if os.path.isfile(fc):
            t = re.search(r'CURRENT_SCHEMA_VERSION\s*=\s*"([^"]+)"', read(fc))
            if t and t.group(1) != want:
                self.add("SCHEMA_VERSION_SYNC", "scripts/doc-format-check.py",
                         f"CURRENT_SCHEMA_VERSION={t.group(1)}\uff0c\u624b\u518c\u662f {want}")

        # 任何脚本里写死 "schema_version: <n>" 字面量都算漂移风险。
        # SCHEMA_VERSION_EXEMPT 中的脚本例外：其 fixture 故意包含过时版本，
        # 用来验证 OUTDATED_SCHEMA_VERSION 检测本身能工作。
        for n in sorted(self.script_names - SCHEMA_VERSION_EXEMPT):
            for t in re.finditer(r"^schema_version:\s*(\d+)\s*$",
                                 read(os.path.join(self.scripts_dir, n)), re.M):
                if t.group(1) != want:
                    self.add("SCHEMA_VERSION_SYNC", f"scripts/{n}",
                             f"\u786c\u7f16\u7801 schema_version: {t.group(1)}"
                             f"\uff0c\u624b\u518c\u662f {want}")

    # -- 10. phrases the manual explicitly forbids -------------------------
    def check_forbidden_phrases(self):
        """The manual bans specific wordings because they contradict actual
        behaviour. The ban itself must be machine checked, otherwise it is just
        another prose rule that drifts.

        Case in point: convert-to-utf8.sh does NOT convert encodings by default,
        yet four SKILL.md files described it as "automatically detects and fixes
        GBK". Manual section 6.1 now forbids that wording.
        """
        banned = (
            "\u81ea\u52a8\u68c0\u6d4b\u5e76\u4fee\u590d GBK",   # auto-detect and fix GBK
            "\u81ea\u52a8\u4fee\u590d GBK",                     # auto-fix GBK
            "\u4e00\u6b21\u6027\u5904\u7406\u7f16\u7801\u8f6c\u6362",  # one-shot encoding conversion
        )
        for label, text in self.corpus():
            for phrase in banned:
                for match in re.finditer(re.escape(phrase), text):
                    start = text.rfind("\n", 0, match.start()) + 1
                    end = text.find("\n", match.end())
                    line = text[start:] if end == -1 else text[start:end]
                    # Only the sentence defining the ban may quote it. A ban in
                    # one place must not suppress contradictory uses elsewhere.
                    if label.startswith("manual/") and "\u4e0d\u5f97\u628a" in line:
                        continue
                    self.add("FORBIDDEN_PHRASE", label,
                             f"\u201c{phrase}\u201d \u4e0e\u811a\u672c\u5b9e\u9645\u884c\u4e3a\u77db\u76fe"
                             f"\uff08\u624b\u518c \u00a76.1 \u5df2\u7981\u7528\u6b64\u8bf4\u6cd5\uff09")

    # -- 11. every script is registered in the manual's script table -------
    def check_script_registry(self):
        """A script that exists but is undocumented drifts silently. This is how
        selftest.py and doc-lint-consistency.py themselves went unregistered."""
        if not self.manual:
            return
        sec = re.search(r"^##\s+16\..*", self.manual, re.S | re.M)
        if not sec:
            return
        body = sec.group(0)
        registered = set(re.findall(r"^\|\s*`([A-Za-z0-9_-]+\.(?:py|sh))`", body, re.M))
        for name in sorted(self.script_names - registered):
            self.add("SCRIPT_REGISTRY_SYNC", "manual/doc-system.md",
                     f"scripts/{name} 存在，但 §16 脚本表未登记")

    # -- 12. templates -----------------------------------------------------
    def check_template_refs(self):
        for label, text in self.corpus():
            for m in re.finditer(r"templates/([A-Za-z0-9_.-]+\.md)", text):
                fname = m.group(1)
                if not os.path.isfile(os.path.join(self.templates_dir, fname)):
                    self.add("TEMPLATE_REF", label, f"templates/{fname} 不存在")

    def run(self):
        self.check_section_refs()
        self.check_script_refs()
        self.check_script_flags()
        self.check_status_codes()
        self.check_schema_sync()
        self.check_home_paths()
        self.check_skill_registry()
        self.check_skill_numbering()
        self.check_schema_version_sync()
        self.check_forbidden_phrases()
        self.check_script_registry()
        self.check_template_refs()
        return self.findings


def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.isdir(os.path.join(root, "scripts")):
        print(f"ERROR: {root} 下没有 scripts/，不像是 doc-system 包根目录")
        sys.exit(2)

    findings = Lint(root).run()
    if findings:
        for f in findings:
            print(f)
        print(f"\n[汇总] {len(findings)} 项引用层不一致")
        sys.exit(1)
    print("ALL_PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
