"""Retrieval evaluation on tests/eval/questions.yaml.

    python -m insurance_gpt.retrieval.evaluate                  # as ChatGPT calls it: German query + question
    python -m insurance_gpt.retrieval.evaluate --untranslated   # worst case: question only, no German query
    python -m insurance_gpt.retrieval.evaluate --tuning FILE    # try a variant of tuning.yaml

Reports hit@1 / hit@k / MRR for in-scope questions, the rejection rate for questions search must reject,
and the relevance scores of both groups so min_relevance can be calibrated. Questions about other insurance
products (reject_by: model) are listed but not scored; ChatGPT has to decline those. The targets, k and all
retrieval settings come from tuning.yaml; the exit code is 1 when a target is missed.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from insurance_gpt.config import PROJECT_ROOT, get_settings
from insurance_gpt.retrieval.search import Retriever
from insurance_gpt.tuning import Evaluation, Tuning, get_tuning, load_tuning

QUESTIONS_FILE = PROJECT_ROOT / "tests" / "eval" / "questions.yaml"


@dataclass
class Outcome:
    id: str
    in_scope: bool
    reject_by: str | None  # "search" | "model" for out-of-scope questions
    rank: int | None  # 1-based rank of the first expected chunk, None if not in top k
    relevant: bool
    best_relevance: float


@dataclass
class Report:
    outcomes: list[Outcome]
    k: int

    @property
    def in_scope(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.in_scope]

    @property
    def search_rejects(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.reject_by == "search"]

    def hit_at(self, n: int) -> float:
        return sum(o.rank is not None and o.rank <= n and o.relevant for o in self.in_scope) / len(self.in_scope)

    @property
    def mrr(self) -> float:
        return sum(1 / o.rank for o in self.in_scope if o.rank and o.relevant) / len(self.in_scope)

    @property
    def rejection_rate(self) -> float:
        return sum(not o.relevant for o in self.search_rejects) / len(self.search_rejects)

    def failures(self, targets: Evaluation) -> list[str]:
        """Missed targets, e.g. ["hit@5 0.85 < 0.9"]; empty when all are met."""
        checks = [
            (f"hit@{self.k}", self.hit_at(self.k), targets.min_hit_at_k),
            ("MRR", self.mrr, targets.min_mrr),
            ("unrelated rejected", self.rejection_rate, targets.min_rejection_rate),
        ]
        return [f"{name} {value:.2f} < {target}" for name, value, target in checks if value < target]


SHORTHANDS = {
    "U:": "ergo-zahntarife-uebersicht-2024-08:uebersicht:",
    "B:": "ergo-zahn-broschuere-2022-07:broschuere:",
}


def _expand(chunk_id: str) -> str:
    for short, full in SHORTHANDS.items():
        if chunk_id.startswith(short):
            return full + chunk_id[len(short) :]
    return chunk_id


def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        questions = yaml.safe_load(f)["questions"]
    for q in questions:
        q["expected"] = [_expand(cid) for cid in q["expected"]]
    return questions


def evaluate(retriever: Retriever, k: int, untranslated: bool = False) -> Report:
    outcomes = []
    for q in load_questions():
        query = q["question"] if untranslated else q["query"]
        hits, relevant = retriever.search(query, None if untranslated else q["question"], top_k=k)
        ids = [h.chunk.chunk_id for h in hits]
        rank = next((i for i, cid in enumerate(ids, start=1) if cid in q["expected"]), None)
        best = max((h.relevance for h in hits), default=0.0)
        outcomes.append(Outcome(q["id"], bool(q["expected"]), q.get("reject_by"), rank, relevant, best))
    return Report(outcomes, k)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m insurance_gpt.retrieval.evaluate")
    parser.add_argument("--untranslated", action="store_true", help="search with the raw question only")
    parser.add_argument("--tuning", type=Path, help="tuning file to use instead of tuning.yaml")
    args = parser.parse_args()
    tuning: Tuning = load_tuning(args.tuning) if args.tuning else get_tuning()
    r = tuning.retrieval
    print(
        f"tuning: {tuning.source}\n  {r.dense_model} | {r.mode} | headings={r.embed_headings} "
        f"| with_question={r.search_with_question} | prefetch={r.prefetch_limit} | min_relevance={r.min_relevance}"
        f" | chunks {tuning.chunking.target_chars}/{tuning.chunking.max_chars} chars\n"
    )
    report = evaluate(Retriever(get_settings(), r), tuning.evaluation.k, args.untranslated)
    for o in report.outcomes:
        if o.in_scope:
            status = ("ok " if o.rank and o.relevant else "MISS") + f" rank={o.rank}"
        elif o.reject_by == "search":
            status = "ok  rejected" if not o.relevant else "MISS accepted"
        else:
            status = "(model) " + ("rejected" if not o.relevant else "passages")
        print(f"{o.id:28} {status:18} best_relevance={o.best_relevance:.3f}")
    in_scores = sorted(o.best_relevance for o in report.in_scope)
    out_scores = sorted(o.best_relevance for o in report.search_rejects)
    print(
        f"\nhit@1={report.hit_at(1):.2f}  hit@{report.k}={report.hit_at(report.k):.2f}  MRR={report.mrr:.2f}  "
        f"unrelated rejected={report.rejection_rate:.2f}"
    )
    print(f"best relevance in-scope: min={in_scores[0]:.3f}  unrelated: max={out_scores[-1]:.3f}")
    failures = report.failures(tuning.evaluation)
    print("targets: " + ("all met" if not failures else "MISSED " + "; ".join(failures)))
    if failures and not args.untranslated:
        sys.exit(1)


if __name__ == "__main__":
    main()
