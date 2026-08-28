# backend/app/services/dependency_analyzer.py
"""
DependencyAnalyzer — Dependency Intelligence Engine
=====================================================
Parses and analyzes project dependency manifests:
  - requirements.txt   (Python pip)
  - pyproject.toml     (Python Poetry / PEP 517)
  - package.json       (Node.js npm/yarn)
  - pom.xml            (Java Maven)

Produces:
  - Total dependency count
  - Direct vs dev dependency split
  - Risk score based on deprecated/ancient packages
  - Outdated package detection (offline heuristic — no external API calls)
  - Dependency risk flags (known deprecated packages)

Risk Score (0-100): 100 = clean, deductions per flag
"""

import json
import logging
import re
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Known deprecated / high-risk packages (offline, curated list)
_DEPRECATED_PYTHON = {
    "flask-sqlalchemy": "Use SQLAlchemy directly or SQLModel",
    "pycrypto": "Replaced by pycryptodome — has known vulnerabilities",
    "md5": "Insecure hash — use hashlib.sha256",
    "urllib3": "Pin to >= 2.0.0 to avoid known CVEs",
    "requests": "Pin to >= 2.31.0 to avoid CVEs",
    "pillow": "Pin to >= 10.0.1 to avoid CVEs",
    "django": "Pin to >= 4.2.0 (LTS) to avoid EOL versions",
    "cryptography": "Pin to >= 41.0.0 to avoid known CVEs",
    "twisted": "Pin to >= 23.8.0",
    "paramiko": "Pin to >= 3.4.0 to avoid CVEs",
    "sqlalchemy": "Pin to >= 2.0.0 for modern async support",
}

_DEPRECATED_NODE = {
    "request": "Deprecated — use axios, node-fetch, or got",
    "moment": "Large bundle — consider date-fns or dayjs",
    "lodash": "Consider native JS alternatives",
    "node-uuid": "Replaced by the 'uuid' package",
    "jade": "Renamed to pug",
    "colors": "Known supply chain attack vector",
    "event-stream": "Known supply chain attack",
    "left-pad": "Infamous npm leftpad incident",
}

_DEPRECATED_JAVA = {
    "commons-collections:3": "Vulnerable to Java deserialization attacks",
    "log4j:1": "Replaced by log4j2; log4j 1.x is EOL",
    "struts2": "Known RCE vulnerabilities in old versions",
}


class DependencyAnalyzer:
    """
    Analyzes dependency manifests and produces intelligence data.
    """

    @classmethod
    def analyze(cls, workspace_path: Path, repo_id: str) -> Dict[str, Any]:
        """
        Scans workspace for dependency manifests and builds the intelligence report.

        Returns:
            {
              "total_count":     int,
              "direct_count":    int,
              "dev_count":       int,
              "risk_score":      int (0-100),
              "outdated_count":  int,
              "flagged_packages":[ { name, reason, severity } ],
              "dependencies":    [ { name, version, type, flagged } ],
              "manifest_type":   str,
              "manifest_files":  [ str ],
            }
        """
        results = {
            "total_count":     0,
            "direct_count":    0,
            "dev_count":       0,
            "risk_score":      100,
            "outdated_count":  0,
            "flagged_packages":[],
            "dependencies":    [],
            "manifest_type":   "none",
            "manifest_files":  [],
        }

        # Try each manifest type in priority order
        manifest_data = None
        for parser, manifest_type in [
            (cls._parse_requirements_txt, "pip"),
            (cls._parse_pyproject_toml,   "poetry"),
            (cls._parse_package_json,     "npm"),
            (cls._parse_pom_xml,          "maven"),
            (cls._parse_pipfile,          "pipenv"),
            (cls._parse_build_gradle,     "gradle"),
            (cls._parse_cargo_toml,       "cargo"),
            (cls._parse_go_mod,           "go"),
        ]:
            data = parser(workspace_path)
            if data:
                if manifest_data is None:
                    manifest_data = data
                    results["manifest_type"] = manifest_type
                    results["manifest_files"] = data["files"]
                else:
                    # Merge additional manifests
                    manifest_data["direct"].extend(data["direct"])
                    manifest_data["dev"].extend(data["dev"])
                    results["manifest_files"].extend(data["files"])

        if manifest_data is None:
            cls._save(repo_id, results)
            return results

        # ── Build dependency list ─────────────────────────────────────────
        all_deps: List[Dict[str, Any]] = []
        flagged: List[Dict[str, Any]] = []
        risk_deductions = 0

        for dep in manifest_data.get("direct", []):
            entry = {
                "name":    dep["name"],
                "version": dep.get("version", "*"),
                "type":    "direct",
                "flagged": False,
                "flag_reason": None,
            }
            flag = cls._check_flag(dep["name"], dep.get("version", ""), results["manifest_type"])
            if flag:
                entry["flagged"] = True
                entry["flag_reason"] = flag["reason"]
                flagged.append({"name": dep["name"], "reason": flag["reason"], "severity": flag["severity"]})
                risk_deductions += {"HIGH": 15, "MEDIUM": 8, "LOW": 3}.get(flag["severity"], 3)
            all_deps.append(entry)

        for dep in manifest_data.get("dev", []):
            entry = {
                "name":    dep["name"],
                "version": dep.get("version", "*"),
                "type":    "dev",
                "flagged": False,
                "flag_reason": None,
            }
            flag = cls._check_flag(dep["name"], dep.get("version", ""), results["manifest_type"])
            if flag:
                entry["flagged"] = True
                entry["flag_reason"] = flag["reason"]
                flagged.append({"name": dep["name"], "reason": flag["reason"], "severity": flag["severity"]})
                risk_deductions += {"HIGH": 10, "MEDIUM": 5, "LOW": 2}.get(flag["severity"], 2)
            all_deps.append(entry)

        # OSV Vulnerability Check
        osv_flags, osv_deductions = cls._check_osv_vulnerabilities(all_deps, results["manifest_type"])
        flagged.extend(osv_flags)
        risk_deductions += osv_deductions

        # ── Compute results ───────────────────────────────────────────────
        results["dependencies"]    = all_deps[:100]  # cap display at 100
        results["flagged_packages"]= flagged
        results["direct_count"]    = len(manifest_data.get("direct", []))
        results["dev_count"]       = len(manifest_data.get("dev", []))
        results["total_count"]     = results["direct_count"] + results["dev_count"]
        results["outdated_count"]  = len(flagged)
        results["risk_score"]      = max(0, min(100, 100 - risk_deductions))

        cls._save(repo_id, results)
        logger.info(
            f"[Deps] '{repo_id}' total={results['total_count']} "
            f"flagged={len(flagged)} risk={results['risk_score']}"
        )
        return results

    # ── Manifest Parsers ──────────────────────────────────────────────────────

    @classmethod
    def _parse_requirements_txt(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse requirements.txt and requirements*.txt files."""
        direct: List[Dict] = []
        files: List[str] = []
        for fname in ["requirements.txt", "requirements-dev.txt", "requirements-test.txt"]:
            fpath = workspace_path / fname
            if not fpath.exists():
                continue
            files.append(fname)
            is_dev = "dev" in fname or "test" in fname
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("-"):
                            continue
                        # Parse: name>=version or name==version or name
                        m = re.match(r'^([A-Za-z0-9_\-\.]+)\s*([><=!~]{0,2})\s*([^\s;#]*)', line)
                        if m:
                            name, op, ver = m.group(1), m.group(2), m.group(3)
                            direct.append({
                                "name":    name.lower(),
                                "version": f"{op}{ver}" if ver else "*",
                                "is_dev":  is_dev,
                            })
            except Exception:
                pass
        if not direct:
            return None
        return {"direct": direct, "dev": [], "files": files}

    @classmethod
    def _parse_pyproject_toml(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse pyproject.toml [tool.poetry.dependencies] section."""
        fpath = workspace_path / "pyproject.toml"
        if not fpath.exists():
            return None
        direct: List[Dict] = []
        dev: List[Dict] = []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Simple regex extraction of [tool.poetry.dependencies] section
            in_deps = False
            in_dev = False
            for line in content.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("[tool.poetry.dependencies]"):
                    in_deps, in_dev = True, False
                    continue
                elif line_stripped.startswith("[tool.poetry.dev-dependencies]") or \
                     line_stripped.startswith("[tool.poetry.group.dev.dependencies]"):
                    in_deps, in_dev = False, True
                    continue
                elif line_stripped.startswith("["):
                    in_deps, in_dev = False, False
                    continue

                if in_deps or in_dev:
                    m = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*=\s*["\'^]?([^"\'#\n\s]*)', line_stripped)
                    if m and m.group(1) != "python":
                        pkg = {"name": m.group(1).lower(), "version": m.group(2) or "*"}
                        if in_dev:
                            dev.append(pkg)
                        else:
                            direct.append(pkg)
        except Exception:
            pass
        if not direct and not dev:
            return None
        return {"direct": direct, "dev": dev, "files": ["pyproject.toml"]}

    @classmethod
    def _parse_package_json(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse package.json dependencies and devDependencies."""
        fpath = workspace_path / "package.json"
        if not fpath.exists():
            return None
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            direct = [
                {"name": k.lower(), "version": v}
                for k, v in data.get("dependencies", {}).items()
            ]
            dev = [
                {"name": k.lower(), "version": v}
                for k, v in data.get("devDependencies", {}).items()
            ]
            if not direct and not dev:
                return None
            return {"direct": direct, "dev": dev, "files": ["package.json"]}
        except Exception:
            return None

    @classmethod
    def _parse_pom_xml(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse pom.xml <dependency> blocks."""
        fpath = workspace_path / "pom.xml"
        if not fpath.exists():
            return None
        direct: List[Dict] = []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Extract groupId:artifactId:version triplets
            deps = re.findall(
                r'<dependency>.*?<groupId>(.*?)</groupId>.*?<artifactId>(.*?)</artifactId>.*?(?:<version>(.*?)</version>)?.*?</dependency>',
                content,
                re.DOTALL
            )
            for group, artifact, version in deps:
                direct.append({
                    "name":    f"{group.strip()}:{artifact.strip()}",
                    "version": version.strip() if version else "*",
                })
        except Exception:
            pass
        if not direct:
            return None
        return {"direct": direct, "dev": [], "files": ["pom.xml"]}

    @classmethod
    def _parse_pipfile(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse Pipfile."""
        fpath = workspace_path / "Pipfile"
        if not fpath.exists():
            return None
        direct, dev = [], []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            in_packages, in_dev = False, False
            for line in content.splitlines():
                line = line.strip()
                if line == "[packages]":
                    in_packages, in_dev = True, False
                    continue
                elif line == "[dev-packages]":
                    in_packages, in_dev = False, True
                    continue
                elif line.startswith("["):
                    in_packages, in_dev = False, False
                    continue
                if (in_packages or in_dev) and "=" in line:
                    parts = line.split("=")
                    name = parts[0].strip().strip('"').strip("'")
                    version = parts[1].strip().strip('"').strip("'")
                    if in_packages:
                        direct.append({"name": name, "version": version})
                    else:
                        dev.append({"name": name, "version": version})
        except Exception:
            pass
        if not direct and not dev:
            return None
        return {"direct": direct, "dev": dev, "files": ["Pipfile"]}

    @classmethod
    def _parse_build_gradle(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse build.gradle dependencies."""
        fpath = workspace_path / "build.gradle"
        if not fpath.exists():
            fpath = workspace_path / "build.gradle.kts"
            if not fpath.exists():
                return None
        direct, dev = [], []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # simple regex to find implementation, testImplementation, api, etc
            matches = re.findall(r'(implementation|testImplementation|api|compileOnly)\s+[\'"]([^\'"]+)', content)
            for scope, dep in matches:
                if scope.startswith("test"):
                    dev.append({"name": dep, "version": "*"})
                else:
                    direct.append({"name": dep, "version": "*"})
        except Exception:
            pass
        if not direct and not dev:
            return None
        return {"direct": direct, "dev": dev, "files": [fpath.name]}

    @classmethod
    def _parse_cargo_toml(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse Cargo.toml."""
        fpath = workspace_path / "Cargo.toml"
        if not fpath.exists():
            return None
        direct, dev = [], []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            in_deps, in_dev = False, False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("[dependencies]"):
                    in_deps, in_dev = True, False
                    continue
                elif line.startswith("[dev-dependencies]"):
                    in_deps, in_dev = False, True
                    continue
                elif line.startswith("["):
                    in_deps, in_dev = False, False
                    continue
                if (in_deps or in_dev) and "=" in line:
                    parts = line.split("=")
                    name = parts[0].strip()
                    if in_deps:
                        direct.append({"name": name, "version": "*"})
                    else:
                        dev.append({"name": name, "version": "*"})
        except Exception:
            pass
        if not direct and not dev:
            return None
        return {"direct": direct, "dev": dev, "files": ["Cargo.toml"]}

    @classmethod
    def _parse_go_mod(cls, workspace_path: Path) -> Optional[Dict]:
        """Parse go.mod."""
        fpath = workspace_path / "go.mod"
        if not fpath.exists():
            return None
        direct = []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            in_require = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                elif line.startswith("require "):
                    parts = line.split()
                    if len(parts) >= 3:
                        direct.append({"name": parts[1], "version": parts[2]})
                    continue
                elif line == ")":
                    in_require = False
                    continue
                if in_require and line and not line.startswith("//"):
                    parts = line.split()
                    if len(parts) >= 2:
                        direct.append({"name": parts[0], "version": parts[1]})
        except Exception:
            pass
        if not direct:
            return None
        return {"direct": direct, "dev": [], "files": ["go.mod"]}

    # ── Risk Flagging ─────────────────────────────────────────────────────────

    @classmethod
    def _check_flag(cls, name: str, version: str, manifest_type: str) -> Optional[Dict]:
        """Returns flag info dict if package is deprecated/risky, else None."""
        name_lower = name.lower()
        if manifest_type in ("pip", "poetry"):
            for pkg, reason in _DEPRECATED_PYTHON.items():
                if name_lower == pkg.lower():
                    return {"reason": reason, "severity": "HIGH"}
        elif manifest_type == "npm":
            for pkg, reason in _DEPRECATED_NODE.items():
                if name_lower == pkg.lower():
                    return {"reason": reason, "severity": "MEDIUM"}
        elif manifest_type == "maven":
            for pkg, reason in _DEPRECATED_JAVA.items():
                if pkg.lower() in name_lower:
                    return {"reason": reason, "severity": "HIGH"}
        return None

    @classmethod
    def _check_osv_vulnerabilities(cls, deps: List[Dict[str, Any]], manifest_type: str) -> tuple[List[Dict[str, Any]], int]:
        ecosystem_map = {
            "pip": "PyPI",
            "poetry": "PyPI",
            "pipenv": "PyPI",
            "npm": "npm",
            "maven": "Maven",
            "gradle": "Maven",
            "cargo": "crates.io",
            "go": "Go"
        }
        ecosystem = ecosystem_map.get(manifest_type)
        if not ecosystem or not deps:
            return [], 0

        queries = []
        # Create map to link query index back to dep
        query_map = {}
        for idx, dep in enumerate(deps):
            version = re.sub(r'^[^\d]*', '', dep["version"]) # Strip ^, ~, >= etc
            if not version or version == '*':
                continue
            queries.append({
                "package": {"name": dep["name"], "ecosystem": ecosystem},
                "version": version
            })
            query_map[len(queries)-1] = dep

        if not queries:
            return [], 0

        flagged = []
        deductions = 0
        try:
            resp = requests.post("https://api.osv.dev/v1/querybatch", json={"queries": queries}, timeout=5)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for idx, result in enumerate(results):
                    vulns = result.get("vulns", [])
                    if vulns:
                        dep = query_map[idx]
                        cves = [v.get("aliases", []) for v in vulns]
                        cve_list = [item for sublist in cves for item in sublist if item.startswith("CVE-")]
                        vuln_id = cve_list[0] if cve_list else vulns[0].get("id")
                        reason = f"Vulnerable to {vuln_id}"
                        
                        # Calculate severity based on OSV aliases or assume HIGH if multiple
                        severity = "HIGH" if len(vulns) > 1 else "MEDIUM"
                        
                        dep["flagged"] = True
                        dep["flag_reason"] = reason
                        flagged.append({"name": dep["name"], "reason": reason, "severity": severity})
                        deductions += {"HIGH": 15, "MEDIUM": 8, "LOW": 3}.get(severity, 8)
        except Exception as e:
            logger.warning(f"[OSV] Query failed: {e}")

        return flagged, deductions

    # ── Persistence ───────────────────────────────────────────────────────────

    @classmethod
    def _save(cls, repo_id: str, result: Dict[str, Any]) -> None:
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "dependencies.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.warning(f"[Deps] Failed to save dependencies.json: {e}")

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads cached dependencies.json."""
        path = settings.REPORTS_DIR / repo_id / "dependencies.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
