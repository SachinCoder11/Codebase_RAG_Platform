# backend/app/services/architecture_analyzer.py
"""
ArchitectureAnalyzer — Repository Architecture Intelligence Engine
==================================================================
Detects and documents the architectural patterns, technology stack,
and structural characteristics of a software repository.

Detects:
  - Application type (REST API, Web App, CLI, Library, etc.)
  - Framework (FastAPI, Django, Express, Spring Boot, etc.)
  - Entry points
  - Route/controller layer
  - Service layer
  - Data models
  - Middleware
  - Database layer (ORM / driver)
  - Authentication mechanism
  - Deployment configuration (Docker, Kubernetes)
  - CI/CD pipeline
  - Dependency injection patterns

Outputs:
  - Architecture summary dict (used in repository_processor.py)
  - ARCHITECTURE_SUMMARY.md report file
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class ArchitectureAnalyzer:
    """
    Enhanced architecture detection engine.
    """

    # ── Entry points ──────────────────────────────────────────────────────────
    _ENTRYPOINT_NAMES = {
        "main.py", "app.py", "index.js", "app.js", "server.js",
        "main.ts", "index.ts", "server.ts", "wsgi.py", "asgi.py",
        "Application.java", "Program.cs", "main.go",
    }

    # ── Framework detection signals ───────────────────────────────────────────
    _FRAMEWORK_SIGNALS: Dict[str, List[str]] = {
        "FastAPI":      ["from fastapi import", "FastAPI()", "APIRouter", "@app.get", "@app.post", "@router.get"],
        "Django":       ["from django", "django.db.models", "urlpatterns", "from django.core"],
        "Flask":        ["from flask import", "Flask(__name__)", "@app.route"],
        "Express":      ["require('express')", "express()", "app.listen", "router.get(", "router.post("],
        "NestJS":       ["@Controller", "@Module", "@Injectable", "NestFactory"],
        "Spring Boot":  ["@SpringBootApplication", "@RestController", "org.springframework"],
        "ASP.NET":      ["using Microsoft.AspNetCore", "[ApiController]", "app.MapGet"],
        "Next.js":      ["from 'next'", "getServerSideProps", "getStaticProps", "next/router"],
        "React":        ["import React", "from 'react'", "useState", "useEffect", "jsx"],
        "Vue":          ["Vue.createApp", "defineComponent", "from 'vue'"],
    }

    # ── Database / ORM signals ────────────────────────────────────────────────
    _DB_SIGNALS: Dict[str, List[str]] = {
        "SQLAlchemy":   ["from sqlalchemy", "create_engine", "Session", "Base = declarative_base"],
        "SQLModel":     ["from sqlmodel import", "SQLModel", "Field(primary_key"],
        "Django ORM":   ["models.Model", "objects.filter", "objects.get"],
        "Prisma":       ["@prisma/client", "PrismaClient", "prisma.user"],
        "TypeORM":      ["@Entity", "@Column", "createConnection", "DataSource"],
        "Mongoose":     ["mongoose.Schema", "mongoose.model", "require('mongoose')"],
        "Tortoise ORM": ["from tortoise", "tortoise.fields"],
        "SQLite":       ["sqlite3.connect", ":memory:", ".db", "sqlite:///"],
        "PostgreSQL":   ["psycopg2", "asyncpg", "postgres://", "postgresql://"],
        "MongoDB":      ["pymongo", "MongoClient", "mongodb://"],
        "Redis":        ["redis.Redis", "aioredis", "redis://"],
    }

    # ── Auth mechanism signals ────────────────────────────────────────────────
    _AUTH_SIGNALS: Dict[str, List[str]] = {
        "JWT":          ["jwt.encode", "jwt.decode", "Bearer", "JWT", "access_token"],
        "OAuth2":       ["OAuth2", "oauth2_scheme", "oauth2_password_bearer", "OAuth2PasswordBearer"],
        "API Key":      ["x-api-key", "api_key", "X-API-Key"],
        "Session":      ["session['user']", "request.session", "SessionMiddleware"],
        "HTTP Basic":   ["HTTPBasicCredentials", "http_basic", "HTTP Basic"],
        "Passport.js":  ["passport.use", "passport.authenticate", "require('passport')"],
        "Auth0":        ["auth0.com", "Auth0Client", "auth0"],
        "Firebase Auth":["firebase-admin", "verify_id_token", "firebase.auth()"],
    }

    # ── App type detection ────────────────────────────────────────────────────
    _APP_TYPE_SIGNALS: Dict[str, List[str]] = {
        "REST API":     ["APIRouter", "@app.get", "app.use(", "@RestController", "app.MapGet"],
        "Web Application": ["render_template", "getServerSideProps", "index.html", "views.py"],
        "CLI Tool":     ["argparse", "click.command", "typer", "sys.argv"],
        "Library":      ["setup.py", "pyproject.toml", "__all__", "setup(name="],
        "Microservice": ["grpc", "protobuf", "message_queue", "rabbitmq", "kafka"],
        "Data Pipeline":["airflow", "prefect", "dagster", "etl", "spark"],
        "ML Service":   ["torch", "tensorflow", "sklearn", "model.predict", "inference"],
    }

    @classmethod
    def analyze(cls, workspace_path: Path, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main analysis entry point. Called by repository_processor.py.

        Returns:
            Architecture summary dict including entrypoints, routes,
            services, models, middlewares, detected frameworks, etc.
        """
        # Collect all file content snippets for signal detection
        # (read first 100 lines of each source file for efficiency)
        content_corpus: List[str] = []
        all_file_paths: List[str] = []

        for entity in entities:
            fp = entity.get("file_path", "")
            all_file_paths.append(fp)
            content_corpus.append(entity.get("content", "")[:500])

        # Also scan the actual workspace files for config/infra signals
        workspace_content = cls._read_workspace_signals(workspace_path)

        combined_corpus = "\n".join(content_corpus + workspace_content)

        # ── Detect components ─────────────────────────────────────────────
        frameworks   = cls._detect_frameworks(combined_corpus)
        db_layer     = cls._detect_db(combined_corpus)
        auth         = cls._detect_auth(combined_corpus)
        app_type     = cls._detect_app_type(combined_corpus)
        entrypoints  = cls._detect_entrypoints(entities, all_file_paths)
        deployment   = cls._detect_deployment(workspace_path)
        ci_cd        = cls._detect_cicd(workspace_path)

        # ── Entity categorization ─────────────────────────────────────────
        routes_list:      List[str] = []
        services_list:    List[str] = []
        models_list:      List[str] = []
        middlewares_list: List[str] = []

        for entity in entities:
            fp   = entity.get("file_path", "").lower()
            name = entity.get("name",      "")
            ct   = entity.get("chunk_type", "")

            # Apply semantic chunk_type based on path heuristics
            if ct in ("route",) or "route" in fp or "controller" in fp or "routes/" in fp:
                entity["chunk_type"] = "route"
                if name and name not in routes_list:
                    routes_list.append(name)

            elif ct in ("service",) or "service" in fp or "service" in name.lower():
                entity["chunk_type"] = "service"
                if name and name not in services_list:
                    services_list.append(name)

            elif ct in ("model",) or "model" in fp or "schema" in fp or "model" in name.lower():
                entity["chunk_type"] = "model"
                if name and name not in models_list:
                    models_list.append(name)

            elif ct in ("middleware",) or "middleware" in fp or "interceptor" in fp:
                entity["chunk_type"] = "middleware"
                if name and name not in middlewares_list:
                    middlewares_list.append(name)

        # ── Build summary ─────────────────────────────────────────────────
        summary = {
            "application_type": app_type,
            "frameworks":       frameworks,
            "entry_points":     entrypoints,
            "routes":           routes_list,
            "services":         services_list,
            "models":           models_list,
            "middlewares":      middlewares_list,
            "database_layer":   db_layer,
            "auth_mechanism":   auth,
            "deployment":       deployment,
            "ci_cd":            ci_cd,
            # Counts for manifest
            "route_count":      len(routes_list),
            "service_count":    len(services_list),
            "model_count":      len(models_list),
            "middleware_count": len(middlewares_list),
        }

        # Write the markdown report
        cls._write_architecture_report(workspace_path, summary)

        logger.info(
            f"[Architecture] type={app_type} frameworks={frameworks} "
            f"db={db_layer} auth={auth} deployment={deployment}"
        )
        return summary

    # ── Detection helpers ─────────────────────────────────────────────────────

    @classmethod
    def _detect_frameworks(cls, corpus: str) -> List[str]:
        detected = []
        for fw, signals in cls._FRAMEWORK_SIGNALS.items():
            if any(s in corpus for s in signals):
                detected.append(fw)
        return detected or ["Unknown"]

    @classmethod
    def _detect_db(cls, corpus: str) -> List[str]:
        detected = []
        for db, signals in cls._DB_SIGNALS.items():
            if any(s in corpus for s in signals):
                detected.append(db)
        return detected or ["Not detected"]

    @classmethod
    def _detect_auth(cls, corpus: str) -> List[str]:
        detected = []
        for auth, signals in cls._AUTH_SIGNALS.items():
            if any(s in corpus for s in signals):
                detected.append(auth)
        return detected or ["Not detected"]

    @classmethod
    def _detect_app_type(cls, corpus: str) -> str:
        scores: Dict[str, int] = {}
        for app_type, signals in cls._APP_TYPE_SIGNALS.items():
            score = sum(1 for s in signals if s in corpus)
            if score > 0:
                scores[app_type] = score
        if not scores:
            return "Unknown"
        return max(scores, key=scores.get)

    @classmethod
    def _detect_entrypoints(
        cls,
        entities: List[Dict[str, Any]],
        all_file_paths: List[str],
    ) -> List[str]:
        eps = []
        for fp in all_file_paths:
            name = Path(fp).name
            if name in cls._ENTRYPOINT_NAMES:
                if fp not in eps:
                    eps.append(fp)
        return eps[:5]

    @classmethod
    def _detect_deployment(cls, workspace_path: Path) -> List[str]:
        signals = []
        checks = {
            "Dockerfile":           "Docker",
            "docker-compose.yml":   "Docker Compose",
            "docker-compose.yaml":  "Docker Compose",
            "kubernetes":           "Kubernetes",
            "k8s":                  "Kubernetes",
            "Procfile":             "Heroku",
            "fly.toml":             "Fly.io",
            "vercel.json":          "Vercel",
            "netlify.toml":         "Netlify",
            "render.yaml":          "Render",
            "serverless.yml":       "Serverless Framework",
        }
        for fname, label in checks.items():
            if (workspace_path / fname).exists() or any(workspace_path.rglob(fname)):
                if label not in signals:
                    signals.append(label)
        return signals or ["Not detected"]

    @classmethod
    def _detect_cicd(cls, workspace_path: Path) -> List[str]:
        signals = []
        checks = {
            ".github/workflows": "GitHub Actions",
            ".circleci":         "CircleCI",
            ".gitlab-ci.yml":    "GitLab CI",
            "Jenkinsfile":       "Jenkins",
            ".travis.yml":       "Travis CI",
            "azure-pipelines.yml": "Azure Pipelines",
        }
        for path_str, label in checks.items():
            if (workspace_path / path_str).exists():
                signals.append(label)
        return signals or ["None detected"]

    @classmethod
    def _read_workspace_signals(cls, workspace_path: Path) -> List[str]:
        """
        Reads key config files in the workspace root for signal detection.
        Limited to first 200 lines each to stay fast.
        """
        snippets = []
        key_files = [
            "requirements.txt", "package.json", "pyproject.toml",
            "setup.py", "pom.xml", "build.gradle",
        ]
        for fname in key_files:
            fpath = workspace_path / fname
            if fpath.exists():
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [next(f) for _ in range(200) if True]
                    snippets.append("".join(lines))
                except Exception:
                    pass
        return snippets

    # ── Report writer ─────────────────────────────────────────────────────────

    @classmethod
    def _write_architecture_report(
        cls,
        workspace_path: Path,
        summary: Dict[str, Any],
    ) -> None:
        """
        Determines repo_id from workspace path and writes ARCHITECTURE_SUMMARY.md.
        """
        try:
            repo_id = workspace_path.name
            report_dir = settings.REPORTS_DIR / repo_id
            report_dir.mkdir(parents=True, exist_ok=True)

            frameworks  = ", ".join(summary.get("frameworks", ["Unknown"]))
            db_layer    = ", ".join(summary.get("database_layer", ["Not detected"]))
            auth        = ", ".join(summary.get("auth_mechanism", ["Not detected"]))
            deployment  = ", ".join(summary.get("deployment", ["Not detected"]))
            ci_cd       = ", ".join(summary.get("ci_cd", ["None detected"]))
            entrypoints = "\n".join(f"  - `{e}`" for e in summary.get("entry_points", []))
            routes      = "\n".join(f"  - `{r}`" for r in summary.get("routes", [])[:20])
            services    = "\n".join(f"  - `{s}`" for s in summary.get("services", [])[:20])
            models      = "\n".join(f"  - `{m}`" for m in summary.get("models", [])[:20])

            md_content = f"""# Architecture Summary

## Overview

| Property | Value |
| :--- | :--- |
| **Application Type** | {summary.get('application_type', 'Unknown')} |
| **Framework(s)**     | {frameworks} |
| **Database Layer**   | {db_layer} |
| **Authentication**   | {auth} |
| **Deployment**       | {deployment} |
| **CI/CD**            | {ci_cd} |

## Entry Points
{entrypoints or '  *None detected*'}

## Routes ({summary.get('route_count', 0)} detected)
{routes or '  *None detected*'}

## Services ({summary.get('service_count', 0)} detected)
{services or '  *None detected*'}

## Models ({summary.get('model_count', 0)} detected)
{models or '  *None detected*'}
"""
            md_path = report_dir / "ARCHITECTURE_SUMMARY.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            logger.info(f"[Architecture] Report written → {md_path}")
        except Exception as e:
            logger.warning(f"[Architecture] Failed to write report: {e}")

    @classmethod
    def format_for_prompt(cls, repo_id: str) -> str:
        """Returns compact XML block for prompt injection from saved summary.json."""
        path = settings.REPORTS_DIR / repo_id / "summary.json"
        if not path.exists():
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            arch = data.get("architecture", {})
            if not arch:
                return ""
            return (
                "<architecture_summary>\n"
                f"  <type>{arch.get('application_type', 'Unknown')}</type>\n"
                f"  <frameworks>{', '.join(arch.get('frameworks', []))}</frameworks>\n"
                f"  <database>{', '.join(arch.get('database_layer', []))}</database>\n"
                f"  <auth>{', '.join(arch.get('auth_mechanism', []))}</auth>\n"
                f"  <deployment>{', '.join(arch.get('deployment', []))}</deployment>\n"
                f"  <entry_points>{', '.join(arch.get('entry_points', []))}</entry_points>\n"
                f"  <route_count>{arch.get('route_count', 0)}</route_count>\n"
                f"  <service_count>{arch.get('service_count', 0)}</service_count>\n"
                f"  <model_count>{arch.get('model_count', 0)}</model_count>\n"
                "</architecture_summary>"
            )
        except Exception:
            return ""
