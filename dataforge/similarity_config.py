from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SimilarityScoringConfig:
    """Конфигурация весов для алгоритма wb_similarity.

    Все значения можно при необходимости параметризовать из UI.
    """

    base_score: int = 100
    max_score: int = 600

    season_match_bonus: int = 80
    season_mismatch_penalty: int = -40  # применяется только если обе сезонности заданы

    color_match_bonus: int = 40
    material_match_bonus: int = 40
    fastener_match_bonus: int = 30

    mega_last_bonus: int = 90
    best_last_bonus: int = 70
    new_last_bonus: int = 50

    model_match_bonus: int = 40

    no_last_penalty_multiplier: float = 0.7  # множитель, если не совпала ни одна колодка

    min_score_threshold: float = 300.0
    max_candidates_per_seed: int = 30
    max_group_size: int | None = 10  # максимальный размер группы (None = без ограничения)

    def validate(self) -> None:
        if self.base_score <= 0:
            raise ValueError("base_score must be > 0")
        if not (0 < self.min_score_threshold < self.max_score):
            raise ValueError("min_score_threshold must be between 0 and max_score")
        if self.max_candidates_per_seed <= 0:
            raise ValueError("max_candidates_per_seed must be > 0")
        if not (0 < self.no_last_penalty_multiplier <= 1):
            raise ValueError("no_last_penalty_multiplier must be in (0,1]")
        if self.max_group_size is not None and self.max_group_size <= 0:
            raise ValueError("max_group_size must be > 0 or None")

    @classmethod
    def from_dict(cls, data: dict | None) -> SimilarityScoringConfig:
        if not data:
            return cls()
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in allowed}
        cfg = cls(**filtered)
        cfg.validate()
        return cfg
