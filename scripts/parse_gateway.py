#!/usr/bin/env python3
"""Parse the VPS-40 LLM-API-Key-Proxy gateway config into a normalized snapshot.

The gateway config lives on VPS 40 (40.233.101.233) at
~/LLM-API-Key-Proxy/config/. In CI the workflow fetches the config over SSH
(restricted VPS_SSH_KEY deploy key) into ./gateway-config and calls this
script. Locally you can point it at any mirror of the config files.

Usage:
    python3 scripts/parse_gateway.py [CONFIG_DIR] [OUTPUT]

The CONFIG_DIR defaults to ./gateway-config (CI's fetch target) and falls
back to other local paths if present.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_yaml(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_config_dir():
    candidates = [
        Path(sys.argv[1]) if len(sys.argv) > 1 else None,
        ROOT / "gateway-config",
        Path.home() / "CodingProjects" / "LLM-API-Key-Proxy" / "config",
        Path("/tmp/gwcfg"),
    ]
    for c in candidates:
        if c and (c / "providers_database.yaml").exists():
            return c
    return None


def provider_display_name(pid: str) -> str:
    """Map internal gateway provider ids to friendly names."""
    overrides = {
        "groq": "Groq",
        "gemini": "Google Gemini API",
        "cerebras": "Cerebras",
        "nvidia": "NVIDIA NIM",
        "mistral": "Mistral",
        "together": "Together AI",
        "openrouter": "OpenRouter",
        "sambanova": "SambaNova",
        "github-models": "GitHub Models",
        "cloudflare": "Cloudflare Workers AI",
        "huggingface": "Hugging Face",
        "fireworks-ai": "Fireworks AI",
        "novita-ai": "Novita AI",
        "siliconflow": "SiliconFlow",
        "siliconflow-cn": "SiliconFlow CN",
        "zhipuai": "Zhipu AI (GLM)",
        "zhipuai-coding-plan": "Zhipu AI coding plan",
        "openai": "OpenAI",
        "kimi-for-coding": "Moonshot Kimi coding",
        "modelscope": "ModelScope",
        "opencode_zen": "OpenCode Zen",
        "aihubmix": "AIHubMix",
        "noobrouter": "NoobRouter",
        "supacoder": "SupaCoder",
        "llmgateway": "LLMGateway",
        "poe": "Poe",
        "zenmux": "ZenMux",
        "wafer.ai": "Wafer.ai",
        "kiro": "Kiro",
        "firepass": "FirePass",
        "orcarouter": "OrcaRouter",
        "poolside": "Poolside",
        "llmtr": "LLMTR",
        "zeldoc": "Zeldoc",
        "subconscious": "Subconscious",
        "kenari": "Kenari",
        "unorouter": "UnoRouter",
        "empiriolabs": "EmpirioLabs",
        "inferx": "InferX",
        "redwakeai": "RedWakeAI",
        "gcli": "GCLI",
        "agnes_ai": "Agnes AI",
        "yungnet": "YungNet",
        "euromodels": "EuroModels",
        "aiand": "AI&",
        "hetzner": "Hetzner",
        "infomaniak": "Infomaniak",
        "regolo-ai": "Regolo AI",
        "merge-gateway": "Merge Gateway",
        "edenai": "Eden AI",
        "larprouter": "LARP Router",
        "scnet-token-plan": "SCNet token plan",
        "septorlabs": "SeptorLabs",
        "freetheai": "FreeTheAI",
        "blaze-free": "Blaze Free",
        "tokenrouter": "TokenRouter",
        "cliproxyapi": "CLIProxyAPI",
        "privaite": "PrivAiTe (local)",
    }
    return overrides.get(pid, pid.replace("_", " ").replace("-", " ").title())


def main():
    cfg_dir = find_config_dir()
    if cfg_dir is None:
        print("ERROR: could not find gateway config directory", file=sys.stderr)
        sys.exit(1)
    print(f"Using config dir: {cfg_dir}")

    providers_db = load_yaml(cfg_dir / "providers_database.yaml") or {}
    virtual_models = load_yaml(cfg_dir / "virtual_models.yaml") or {}
    static_vm = load_yaml(cfg_dir / "static_virtual_models.yaml") or {}
    dead = load_yaml(cfg_dir / "dead_providers.yaml") or {}
    chain_pins = load_yaml(cfg_dir / "chain_pins.yaml") or {}

    providers = providers_db.get("providers", [])
    provider_by_id = {p["id"]: p for p in providers}

    # --- blocked sets for reliability notes ---
    blocked_providers = set()
    blocked_models = set()  # (provider, model)
    blocked_model_prefixes = []  # (provider, model_prefix, allow_models)
    blocked_prefixes = []
    for bp in dead.get("blocked_providers", []):
        blocked_providers.add(bp["provider"])
    for bm in dead.get("blocked_models", []):
        if "model" in bm:
            blocked_models.add((bm["provider"], bm["model"]))
        else:
            blocked_model_prefixes.append(
                (bm["provider"], bm.get("model_prefix"), bm.get("allow_models", []))
            )
    for bpr in dead.get("blocked_provider_prefixes", []):
        blocked_prefixes.append(bpr["prefix"])

    def is_blocked(pid, model_id):
        if pid in blocked_providers:
            return True
        if (pid, model_id) in blocked_models:
            return True
        for bpid, mprefix, allow in blocked_model_prefixes:
            if bpid == pid and mprefix and model_id.startswith(mprefix):
                if model_id not in allow:
                    return True
        if any(pid.startswith(p) for p in blocked_prefixes):
            return True
        return False

    # --- collect free models from providers ---
    models = {}  # key: (provider_id, model_id) -> record
    for p in providers:
        pid = p["id"]
        if not p.get("free_tier"):
            continue
        for fm in p.get("free_models", []):
            mid = fm.get("id")
            if not mid:
                continue
            rec = {
                "provider_id": pid,
                "provider_name": provider_display_name(pid),
                "model_id": mid,
                "context": fm.get("context"),
                "tps": fm.get("tps"),
                "capabilities": fm.get("capabilities", []),
                "notes": fm.get("notes", ""),
                "blocked": is_blocked(pid, mid),
                "source": "gateway",
            }
            models[(pid, mid)] = rec

    # --- virtual model chains: which (provider, model) pairs the gateway serves ---
    all_vm = {}
    for k, v in (virtual_models.get("virtual_models") or {}).items():
        all_vm[k] = v
    for k, v in (static_vm.get("virtual_models") or {}).items():
        all_vm[k] = v

    virtual_served = {}  # (provider, model) -> [virtual model names]
    for vm_name, vm in all_vm.items():
        chain = vm.get("fallback_chain") or []
        for entry in chain:
            key = (entry.get("provider"), entry.get("model"))
            virtual_served.setdefault(key, []).append(vm_name)

    # merge virtual-served info into model records
    for (pid, mid), rec in models.items():
        served = virtual_served.get((pid, mid), [])
        if served:
            rec["virtual_models"] = sorted(set(served))

    # models referenced by virtual chains but not in free_models (still free via gateway)
    for (pid, mid), vms in virtual_served.items():
        if (pid, mid) not in models:
            rec = {
                "provider_id": pid,
                "provider_name": provider_display_name(pid),
                "model_id": mid,
                "context": None,
                "tps": None,
                "capabilities": [],
                "notes": "Served via gateway virtual model chain",
                "blocked": is_blocked(pid, mid),
                "source": "gateway",
                "virtual_models": sorted(set(vms)),
            }
            models[(pid, mid)] = rec

    # --- chain pins (reliability signal: pinned = actively maintained head) ---
    pinned = set()
    for vm_name, entries in chain_pins.items():
        for e in entries:
            pinned.add((e.get("provider"), e.get("model")))

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_note": (
            "Snapshot of VPS-40 LLM-API-Key-Proxy config, auto-refreshed weekly "
            "by the CI workflow via the restricted VPS_SSH_KEY deploy key. "
            "Regenerate manually with scripts/parse_gateway.py <config-dir>."
        ),
        "providers_total": len(providers),
        "providers_free_tier": len([p for p in providers if p.get("free_tier")]),
        "models": sorted(
            [
                {
                    **rec,
                    "pinned": (rec["provider_id"], rec["model_id"]) in pinned,
                }
                for rec in models.values()
            ],
            key=lambda r: (r["provider_id"], r["model_id"]),
        ),
    }
    out_path = DATA / "gateway_models.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path} with {len(output['models'])} model records "
          f"({output['providers_free_tier']} free-tier providers)")


if __name__ == "__main__":
    main()
