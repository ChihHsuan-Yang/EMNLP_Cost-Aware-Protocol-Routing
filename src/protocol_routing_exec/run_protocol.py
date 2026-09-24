#!/usr/bin/env python3
"""Run one (dataset x model x protocol) cell against an OpenAI-compatible endpoint.

    python run_protocol.py \
        --dataset-config  configs/datasets/omnimath.yaml \
        --model-config    configs/models/gpt_oss_120b.yaml \
        --protocol-config configs/protocols/per.yaml \
        --provider-config configs/providers/openai_compatible.example.yaml \
        --output-dir      runs/omnimath_per_oss120b

Use --provider-config configs/providers/mock.yaml for a zero-network, zero-cost
end-to-end exercise of the whole pipeline. Use --dry-run to render prompts
without calling anything at all.

Credentials come from environment variables only and are never written to any
artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("PyYAML is required: pip install pyyaml\n")
    raise

from . import OUTPUT_SCHEMA_VERSION, __version__
from .artifacts import (
    RunLogger, build_resolved_config, environment_snapshot, git_commit,
    scrub_secrets, utc_now, write_answers_csv, write_checksums, write_json,
    write_yaml,
)
from .client import ChatClient, OpenAICompatibleProvider, ProviderError, TokenLedger
from .datasets import dataset_fingerprint, leakage_check, load_dataset
from .evaluator import LlmEvaluator
from .mock_backend import MockProvider
from .protocols import build_protocol


def load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise SystemExit("Config file not found: %s" % path)
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise SystemExit("Config file %s did not parse to a mapping." % path)
    return data


def build_provider(provider_cfg: Dict[str, Any]):
    provider_type = str(provider_cfg.get("provider_type", "")).strip()
    if provider_type == "mock":
        mock = provider_cfg.get("mock", {}) or {}
        return MockProvider(
            seed=int(mock.get("seed", 0)),
            answer_mode=str(mock.get("answer_mode", "mixed")),
            gold_rate=float(mock.get("gold_rate", 0.5)),
            fail_rate=float(mock.get("fail_rate", 0.0)),
            malformed_rate=float(mock.get("malformed_rate", 0.0)))
    if provider_type == "openai_compatible":
        endpoint = provider_cfg.get("endpoint", {}) or {}
        return OpenAICompatibleProvider(
            base_url_env=str(endpoint.get("base_url_env", "INFERENCE_BASE_URL")),
            api_key_env=str(endpoint.get("api_key_env", "INFERENCE_API_KEY")),
            extra_headers=endpoint.get("extra_headers") or {},
            send_auth_header=bool(endpoint.get("send_auth_header", True)))
    raise SystemExit(
        "Unknown provider_type %r. Use 'openai_compatible' or 'mock'." % provider_type)


def resolve_decoding(model_cfg, protocol_cfg, provider_cfg) -> Dict[str, Any]:
    """Merge decoding settings; protocol role overrides are applied per role.

    Precedence: model config < provider transport overrides. Temperature is
    pinned to the model config's value (0.0 for both paper models) and a
    provider config cannot silently raise it.
    """
    decoding = dict(model_cfg.get("decoding", {}) or {})
    transport = dict(provider_cfg.get("transport", {}) or {})
    decoding.setdefault("temperature", 0.0)
    decoding.setdefault("max_tokens", 4096)
    decoding["timeout_seconds"] = float(transport.get("timeout_seconds",
                                        decoding.get("timeout_seconds", 600.0)))
    decoding["max_retries"] = int(transport.get("max_retries",
                                  decoding.get("max_retries", 7)))
    decoding["backoff_cap_seconds"] = float(transport.get("backoff_cap_seconds",
                                            decoding.get("backoff_cap_seconds", 60.0)))
    return decoding


def build_clients(protocol_cfg, model_cfg, evaluator_model_cfg, provider, decoding,
                  ledger, logger, seed):
    """One ChatClient per role. Actor roles use the solver model; the evaluator
    uses its own model config, because the paper fixes the judge to
    gpt-oss-120b for BOTH solver families."""
    clients = {}
    roles = (protocol_cfg.get("roles") or {})
    for role_name, role_spec in roles.items():
        if role_name == "evaluator":
            continue
        clients[role_name] = ChatClient(
            provider=provider,
            model=model_cfg["model_id"],
            temperature=float(decoding["temperature"]),
            max_tokens=int(role_spec.get("max_tokens") or decoding["max_tokens"]),
            timeout_seconds=decoding["timeout_seconds"],
            max_retries=decoding["max_retries"],
            backoff_cap_seconds=decoding["backoff_cap_seconds"],
            ledger=ledger, logger=logger, seed=seed)
    evaluator_role = roles.get("evaluator", {}) or {}
    evaluator_client = ChatClient(
        provider=provider,
        model=evaluator_model_cfg["model_id"],
        temperature=float(evaluator_model_cfg.get("decoding", {}).get("temperature",
                          decoding["temperature"])),
        max_tokens=int(evaluator_role.get("max_tokens")
                       or evaluator_model_cfg.get("decoding", {}).get("max_tokens", 4096)),
        timeout_seconds=decoding["timeout_seconds"],
        max_retries=decoding["max_retries"],
        backoff_cap_seconds=decoding["backoff_cap_seconds"],
        ledger=ledger, logger=logger, seed=seed)
    return clients, evaluator_client, evaluator_role


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_protocol.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset-config", required=True,
                        help="Path to configs/datasets/<name>.yaml")
    parser.add_argument("--model-config", required=True,
                        help="Path to configs/models/<name>.yaml (the SOLVER model)")
    parser.add_argument("--protocol-config", required=True,
                        help="Path to configs/protocols/{baseline,single,per,broadcast}.yaml")
    parser.add_argument("--provider-config", required=True,
                        help="Path to configs/providers/<name>.yaml; use mock.yaml "
                             "for a zero-network run")
    parser.add_argument("--output-dir", required=True,
                        help="Run directory to create. All artifacts land here.")
    parser.add_argument("--evaluator-model-config", default=None,
                        help="Judge model config. Defaults to the model config named "
                             "by the protocol config's evaluator_model_config, which "
                             "is gpt-oss-120b for every paper run, INCLUDING the "
                             "Gemma solver runs.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Run only the first N problems (0 = all).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render one prompt per role and exit. No network, no "
                             "provider construction, no credentials needed.")
    parser.add_argument("--seed", type=int, default=0,
                        help="Seed for retry jitter and the mock backend. Does NOT "
                             "make a real endpoint deterministic.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Allow writing into a non-empty output directory.")
    parser.add_argument("--quiet", action="store_true",
                        help="Do not echo the run log to stdout.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    dataset_cfg = load_yaml(args.dataset_config)
    model_cfg = load_yaml(args.model_config)
    protocol_cfg = load_yaml(args.protocol_config)
    provider_cfg = load_yaml(args.provider_config)

    config_dir = os.path.dirname(os.path.dirname(os.path.abspath(args.protocol_config)))
    evaluator_model_path = args.evaluator_model_config
    if not evaluator_model_path:
        named = protocol_cfg.get("evaluator_model_config")
        if named:
            evaluator_model_path = os.path.join(config_dir, "models", str(named))
        else:
            evaluator_model_path = args.model_config
    evaluator_model_cfg = load_yaml(evaluator_model_path)

    output_dir = os.path.expandvars(os.path.expanduser(args.output_dir))
    if os.path.isdir(output_dir) and os.listdir(output_dir) and not args.overwrite:
        raise SystemExit("Output directory %s is not empty. Pass --overwrite to reuse it."
                         % output_dir)
    os.makedirs(output_dir, exist_ok=True)
    logger = RunLogger(os.path.join(output_dir, "run.log"), echo=not args.quiet)
    logger("runner=%s schema=%s protocol=%s"
           % (__version__, OUTPUT_SCHEMA_VERSION, protocol_cfg.get("protocol_id")))

    decoding = resolve_decoding(model_cfg, protocol_cfg, provider_cfg)

    # -- data ------------------------------------------------------------
    rows = load_dataset(dataset_cfg, limit=args.limit)
    fingerprint = dataset_fingerprint(rows)
    leak = leakage_check(rows)
    write_json(os.path.join(output_dir, "input_leakage_check.json"), leak)
    if not leak["passed"]:
        logger("FATAL input leakage check failed: %s" % leak["errors"][:3])
        raise SystemExit("Input leakage check failed; see input_leakage_check.json")
    logger("loaded %d problems fingerprint=%s" % (len(rows), fingerprint))

    # -- provider --------------------------------------------------------
    if args.dry_run:
        provider = MockProvider(seed=args.seed)
        provider_desc = {"provider_type": "dry_run",
                         "note": "No provider was constructed; prompts only."}
    else:
        try:
            provider = build_provider(provider_cfg)
        except ProviderError as exc:
            logger("FATAL provider error: %s" % exc)
            raise SystemExit(str(exc))
        # MOCK ONLY: hand the fake provider the gold answers through a side
        # channel so its scripted judge can string-compare and its scripted
        # solver can sometimes be "right". Gold NEVER enters a prompt. A real
        # provider has no register_gold method, so this is structurally
        # impossible on a real run. Done BEFORE describe() so the manifest
        # records the true registry size.
        if hasattr(provider, "register_gold"):
            for problem in rows:
                provider.register_gold(problem["input"], problem["answer"])
            logger("mock provider: registered %d gold answers out of band" % len(rows))
        provider_desc = provider.describe()

    # -- resolved config, written BEFORE any call -------------------------
    resolved = build_resolved_config(
        dataset_cfg=dataset_cfg, model_cfg=model_cfg, protocol_cfg=protocol_cfg,
        provider_desc=provider_desc, decoding=decoding, seed=args.seed,
        limit=args.limit, output_dir=output_dir,
        dataset_version=dataset_cfg.get("version"),
        dataset_fingerprint_value=fingerprint,
        prompt_version=protocol_cfg.get("prompt_version"),
        code_commit=git_commit())
    resolved["evaluator_model"] = {
        "id": evaluator_model_cfg.get("model_id"),
        "revision": evaluator_model_cfg.get("model_revision"),
        "revision_status": evaluator_model_cfg.get("model_revision_status"),
        "config_path": os.path.basename(evaluator_model_path),
    }
    write_yaml(os.path.join(output_dir, "resolved_config.yaml"), resolved)
    write_json(os.path.join(output_dir, "environment.json"), environment_snapshot())

    # -- clients + evaluator ----------------------------------------------
    ledger = TokenLedger()
    clients, evaluator_client, evaluator_role = build_clients(
        protocol_cfg, model_cfg, evaluator_model_cfg, provider, decoding,
        ledger, logger, args.seed)
    evaluator = LlmEvaluator(
        client=evaluator_client,
        prepend_template=evaluator_role.get("prepend_prompt", ""),
        append_template=evaluator_role.get("append_prompt", ""),
        dimensions=(protocol_cfg.get("rule", {}) or {}).get(
            "evaluator_dimensions", ["Correctness"]),
        max_parse_retry=int(evaluator_role.get("max_retry", 10)),
        max_tokens=int(evaluator_role.get("max_tokens") or 4096))

    protocol = build_protocol(protocol_cfg, clients, evaluator, logger=logger)

    # -- dry run ------------------------------------------------------------
    if args.dry_run:
        outcome = protocol.run(rows[0], dry_run=True)
        prompts = [e for e in outcome.events if e.get("type") == "dry_run_prompt"]
        write_json(os.path.join(output_dir, "dry_run_prompts.json"), {
            "protocol": protocol_cfg.get("protocol_id"),
            "problem_id": rows[0]["id"],
            "n_prompts": len(prompts),
            "prompts": prompts,
        })
        logger("dry-run rendered %d prompt(s) for protocol=%s"
               % (len(prompts), protocol_cfg.get("protocol_id")))
        for entry in prompts:
            print("\n" + "=" * 78)
            print("PROTOCOL %s | ROLE %s | STAGE %s"
                  % (protocol_cfg.get("protocol_id"), entry["role"], entry["stage"]))
            print("=" * 78)
            print(entry["prompt"])
        write_checksums(output_dir)
        logger.close()
        return 0

    # -- main loop ----------------------------------------------------------
    predictions_path = os.path.join(output_dir, "predictions.jsonl")
    summary_rows: List[Dict[str, Any]] = []
    n_passed = 0
    n_direct_protocol_fail = 0
    n_judge_unparseable = 0
    started = time.time()

    with open(predictions_path, "w", encoding="utf-8") as out:
        for index, problem in enumerate(rows):
            item_started = time.time()
            before = ledger.snapshot()
            try:
                outcome = protocol.run(problem, dry_run=False)
                error = ""
            except Exception as exc:  # noqa: BLE001 - one bad item must not kill the run
                logger("problem %s raised %s: %s" % (problem["id"], type(exc).__name__, exc))
                from .protocols import ProtocolOutcome
                outcome = ProtocolOutcome(stop_reason="exception")
                error = "%s: %s" % (type(exc).__name__, str(exc)[:400])
            after = ledger.snapshot()

            delta = {
                "prompt_tokens": after["prompt_tokens"] - before["prompt_tokens"],
                "completion_tokens": after["completion_tokens"] - before["completion_tokens"],
                "calls": after["calls"] - before["calls"],
                "http_attempts": after["http_attempts"] - before["http_attempts"],
            }
            delta["total_tokens"] = delta["prompt_tokens"] + delta["completion_tokens"]
            last_eval = outcome.evaluations[-1] if outcome.evaluations else None
            judge_calls = sum(e.judge_calls for e in outcome.evaluations)
            direct_fail = bool(last_eval.direct_protocol_fail) if last_eval else False
            unparseable = any(e.judge_unparseable for e in outcome.evaluations)
            n_passed += int(outcome.passed)
            n_direct_protocol_fail += int(direct_fail)
            n_judge_unparseable += int(unparseable)
            wall = round(time.time() - item_started, 3)

            record = {
                "problem_id": problem["id"],
                "protocol": protocol_cfg.get("protocol_id"),
                "model_id": model_cfg.get("model_id"),
                "evaluator_model_id": evaluator_model_cfg.get("model_id"),
                "final_answer": outcome.final_answer,
                "final_text": outcome.final_text,
                "passed": outcome.passed,
                "correctness": 1 if outcome.passed else 0,
                "rounds_used": outcome.rounds_used,
                "stop_reason": outcome.stop_reason,
                "judge_calls": judge_calls,
                "direct_protocol_fail": direct_fail,
                "judge_unparseable": unparseable,
                "evaluations": [e.to_dict() for e in outcome.evaluations],
                "tokens": delta,
                "wall_seconds": wall,
                "error": error,
                "events": outcome.events,
                "output_schema_version": OUTPUT_SCHEMA_VERSION,
            }
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            out.flush()

            summary_rows.append({
                "problem_id": problem["id"],
                "protocol": protocol_cfg.get("protocol_id"),
                "final_answer": outcome.final_answer,
                "passed": outcome.passed,
                "correctness": 1 if outcome.passed else 0,
                "rounds_used": outcome.rounds_used,
                "stop_reason": outcome.stop_reason,
                "judge_calls": judge_calls,
                "direct_protocol_fail": direct_fail,
                "prompt_tokens": delta["prompt_tokens"],
                "completion_tokens": delta["completion_tokens"],
                "total_tokens": delta["total_tokens"],
                "llm_calls": delta["calls"],
                "wall_seconds": wall,
            })
            logger("[%d/%d] %s passed=%s rounds=%d calls=%d tokens=%d"
                   % (index + 1, len(rows), problem["id"], outcome.passed,
                      outcome.rounds_used, delta["calls"], delta["total_tokens"]))

    elapsed = round(time.time() - started, 3)
    write_answers_csv(os.path.join(output_dir, "answers.csv"), summary_rows)
    write_json(os.path.join(output_dir, "token_counts.json"), ledger.snapshot())
    write_json(os.path.join(output_dir, "evaluation.json"), {
        "n_problems": len(rows),
        "n_passed": n_passed,
        "accuracy": (float(n_passed) / len(rows)) if rows else 0.0,
        "n_direct_protocol_fail": n_direct_protocol_fail,
        "n_judge_unparseable": n_judge_unparseable,
        "note": ("direct_protocol_fail counts items where no boxed answer was found "
                 "and the judge was never called. judge_unparseable counts items "
                 "where the judge response never parsed and the item was scored 0 "
                 "-- upstream records these identically to a genuine wrong answer."),
    })

    manifest = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "runner_version": __version__,
        "started_at_utc": utc_now(),
        "elapsed_seconds": elapsed,
        "protocol": protocol_cfg.get("protocol_id"),
        "dataset_id": dataset_cfg.get("dataset_id"),
        "dataset_fingerprint": fingerprint,
        "dataset_rows_loaded": len(rows),
        "dataset_expected_rows": dataset_cfg.get("expected_rows"),
        "model_id": model_cfg.get("model_id"),
        "model_revision": model_cfg.get("model_revision"),
        "evaluator_model_id": evaluator_model_cfg.get("model_id"),
        "provider": provider_desc,
        "decoding": decoding,
        "seed": args.seed,
        "limit": args.limit or None,
        "n_problems": len(rows),
        "n_passed": n_passed,
        "accuracy": (float(n_passed) / len(rows)) if rows else 0.0,
        "tokens": ledger.snapshot(),
        "input_leakage_check": leak,
        "reproducibility_note": (
            "This is a functional rerun, not the paper's historical execution. "
            "The original serving environment is gone and no model snapshot was "
            "pinned. See docs/track_b_requirements.md."),
    }
    leaks = scrub_secrets(manifest)
    if leaks:
        raise SystemExit("Refusing to write manifest: secrets at %s" % leaks)
    write_json(os.path.join(output_dir, "manifest.json"), manifest)

    logger("done: %d/%d passed (%.3f) in %.1fs, %d calls, %d tokens"
           % (n_passed, len(rows), manifest["accuracy"], elapsed,
              ledger.snapshot()["calls"], ledger.snapshot()["total_tokens"]))
    logger.close()
    write_checksums(output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
