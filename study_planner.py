from __future__ import annotations
from dataclasses import dataclass, asdict
from math import ceil
from typing import List, Dict, Optional
import datetime as dt

# =========================
#   Structures de données
# =========================

@dataclass
class ContentBlock:
    """Un bloc homogène de contenu (ex: 'Ch.1 slides', 'Manuel p. 1-50')."""
    units: int                     # nombre d'unités (pages, slides, vidéos)
    unit_type: str                 # 'page' | 'slide' | 'video_min' | 'exo' ...
    difficulty: float = 1.0        # 0.7 (facile) ... 1.0 (moyen) ... 1.3 (difficile)
    novelty: float = 1.0           # 0.7 connu ... 1.0 mixte ... 1.3 nouveau
    density: float = 1.0           # 0.8 aéré ... 1.0 normal ... 1.2 dense

@dataclass
class ExamProfile:
    """Profil d'évaluation pour dimensionner exercices et révisions."""
    weight_theory: float = 0.4     # poids théorie / compréhension
    weight_problems: float = 0.4   # poids résolution d'exos/problèmes
    weight_memorization: float = 0.2# poids par cœur (formules, defs)
    question_mix: Dict[str, float] = None  # ex: {"QCM":0.4,"problèmes":0.5,"rédaction":0.1}

    def __post_init__(self):
        if self.question_mix is None:
            self.question_mix = {"QCM": 0.3, "problèmes": 0.6, "rédaction": 0.1}

@dataclass
class UserProfile:
    """Paramètres individuels."""
    read_speed_page_min: float = 2.5      # min/page (manuel)
    read_speed_slide_min: float = 0.9     # min/slide (avec prises de notes légères)
    video_multiplier: float = 1.0         # 1.0 = vitesse x1 (mettre 0.6 si tu regardes à x1.5-1.75)
    notes_factor: float = 1.15            # +15% si tu prends des notes
    language_penalty: float = 1.0         # 1.1 si langue seconde
    exercise_min_each: float = 7.0        # min par exercice représentatif
    problem_set_size: int = 12            # nb d'exercices « significatifs » pour une bonne couverture
    retention_sensitivity: float = 0.6    # 0.5-0.8 ; impact courbe de l'oubli sur TR
    fatigue_threshold_min: int = 150      # au-delà, rendement décroissant dans une même journée
    fatigue_penalty: float = 1.2          # coût marginal après seuil (20% de temps en plus)
    target_grade: float = 0.8             # 0.5-1.0 (objectif 80% par défaut)
    current_mastery: float = 0.5          # 0-1 (auto-évaluation globale)

@dataclass
class Constraints:
    days_available: int
    max_minutes_per_day: int = 240        # plafond raisonnable/jour
    min_minutes_per_day: int = 60
    blocked_days: Optional[List[int]] = None  # indices de jours (0..D-1) indisponibles

@dataclass
class PlanItem:
    day_index: int
    date: Optional[str]
    learn_min: int
    exercises_min: int
    review_min: int
    mock_min: int

@dataclass
class PlanResult:
    total_minutes: int
    per_day: List[PlanItem]
    breakdown: Dict[str, int]  # {"learn":..., "exercises":..., "review":..., "mock":...}
    params_used: Dict[str, float]

# =========================
#   Coefficients unitaires
# =========================

UNIT_BASE_MIN = {
    "page": 2.5,        # min/page de base (sans coeffs)
    "slide": 1.0,       # min/slide de base (sans coeffs)
    "video_min": 1.0,   # 1 minute de vidéo = 1 minute de temps base
    "exo": 7.0,
}

# =========================
#   Calcul des composantes
# =========================

def estimate_initial_learning_minutes(blocks: List[ContentBlock], user: UserProfile) -> int:
    total = 0.0
    for b in blocks:
        if b.unit_type not in UNIT_BASE_MIN:
            raise ValueError(f"unit_type inconnu: {b.unit_type}")

        base = UNIT_BASE_MIN[b.unit_type] * b.units

        # Adapter aux vitesses personnelles
        if b.unit_type == "page":
            base *= (user.read_speed_page_min / UNIT_BASE_MIN["page"])
        elif b.unit_type == "slide":
            base *= (user.read_speed_slide_min / UNIT_BASE_MIN["slide"])
        elif b.unit_type == "video_min":
            base *= user.video_multiplier
        elif b.unit_type == "exo":
            base *= (user.exercise_min_each / UNIT_BASE_MIN["exo"])

        # Densité, difficulté, nouveauté, prise de notes, langue
        base *= b.density * b.difficulty * b.novelty
        base *= user.notes_factor * user.language_penalty

        total += base

    return int(round(total))


def estimate_exercise_minutes(blocks: List[ContentBlock], exam: ExamProfile, user: UserProfile) -> int:
    """
    Dimensionne un volume d'exos significatifs en fonction du mix de questions
    et du poids 'problems' dans l'évaluation.
    """
    # Taille cible d’un « set » d’exercices représentatifs
    target_set = user.problem_set_size

    # Plus le mix favorise problèmes/rédaction, plus on pousse d'exos
    mix_factor = (exam.question_mix.get("problèmes", 0) * 1.0 +
                  exam.question_mix.get("rédaction", 0) * 0.6 +
                  exam.question_mix.get("QCM", 0) * 0.3)

    # Influence du poids problems dans la note
    weight_factor = 0.7 + 0.6 * exam.weight_problems  # 0.7..1.3

    # Ajustement selon l’écart entre objectif et maîtrise actuelle
    gap = max(0.0, user.target_grade - user.current_mastery)   # 0..1
    gap_factor = 1.0 + 0.7 * gap                                # jusqu’à +70%

    # Un bloc "exo" explicite dans le contenu augmente encore le quota
    explicit_exo_units = sum(b.units for b in blocks if b.unit_type == "exo")
    explicit_exo_bonus = 1.0 + min(0.5, explicit_exo_units / max(1, target_set) * 0.3)

    total_exos = int(round(target_set * mix_factor * weight_factor * gap_factor * explicit_exo_bonus))
    total_exos = max(total_exos, int(round(target_set * 0.6)))  # garde-fou

    minutes = int(round(total_exos * user.exercise_min_each))
    return minutes


def estimate_review_minutes(initial_minutes: int, user: UserProfile, days_available: int) -> int:
    """
    Courbe de l'oubli simplifiée via 3 à 4 vagues de révision.
    Plus il y a de jours, plus on espace et on réalloue du temps à la révision.
    """
    # Part de révision basée sur sensibilité à l’oubli et horizon
    #  Jours courts: moins de vagues; Jours longs: plus de vagues
    if days_available <= 2:
        waves = 1
        frac = 0.20
    elif days_available <= 5:
        waves = 2
        frac = 0.28
    elif days_available <= 10:
        waves = 3
        frac = 0.33
    else:
        waves = 4
        frac = 0.38

    frac *= user.retention_sensitivity  # 0.5-0.8 par défaut

    review_total = int(round(initial_minutes * frac))
    return max(30, review_total)  # un minimum symbolique


def estimate_mock_minutes(days_available: int,
                          want_mocks: bool = True,
                          mock_duration_min: int = 90,
                          review_ratio: float = 0.5) -> int:
    """
    Examens blancs: 1 si fenêtre courte, 2 si >7 jours, sinon optionnel.
    review_ratio = fraction de la durée réallouée au corrigé/retour.
    """
    if not want_mocks:
        return 0
    if days_available <= 4:
        n = 1
    elif days_available <= 10:
        n = 2
    else:
        n = 2
    total = 0
    for _ in range(n):
        total += mock_duration_min               # passation
        total += int(round(mock_duration_min * review_ratio))  # correction/retour
    return total


# =========================
#   Planification par jour
# =========================

def distribute_minutes_over_days(
    learn_min: int,
    exo_min: int,
    review_min: int,
    mock_min: int,
    constraints: Constraints,
    start_date: Optional[dt.date] = None
) -> List[PlanItem]:
    D = constraints.days_available
    blocked = set(constraints.blocked_days or [])
    maxd = constraints.max_minutes_per_day
    mind = constraints.min_minutes_per_day

    # Partitionner par priorité temporelle :
    #  - Apprentissage initial tôt
    #  - Exercices en milieu/fin
    #  - Révisions en vagues (J+1, J+3, J+7 ~ approximées)
    #  - Mocks vers la fin (derniers 40%)
    per_day = [dict(learn=0, exo=0, review=0, mock=0) for _ in range(D)]

    # Helper pour pousser des minutes dans des jours (respectant plafonds/fatigue)
    def push(kind: str, minutes: int, day_order: List[int]):
        remaining = minutes
        for d in day_order:
            if d in blocked:
                continue
            cap = maxd - sum(per_day[d].values())
            if cap <= 0:
                continue
            alloc = min(cap, remaining)
            per_day[d][kind] += alloc
            remaining -= alloc
            # légère pénalité fatigue si dépasse un seuil intrajournalier
            # (on la gère implicitement en réduisant le cap disponible)
            if remaining <= 0:
                break
        return remaining

    # Ordres de priorité et placements
    days_idx = list(range(D))
    last_40 = set(days_idx[int(D*0.6):]) if D > 1 else set([0])

    # 1) Apprentissage initial: pousser dès le début
    rem = push("learn", learn_min, days_idx)
    # si reste (fenêtre trop serrée), overflow en continu
    if rem > 0:
        push("learn", rem, days_idx[::-1])

    # 2) Exercices: milieux et fin (progression)
    order_exo = list(range(D//3, D)) if D >= 3 else days_idx
    rem = push("exo", exo_min, order_exo)
    if rem > 0:
        push("exo", rem, days_idx[::-1])

    # 3) Révisions: placer par vagues approximatives
    # On crée 3 vagues (ou 2 si D petit)
    waves = []
    if D >= 2:
        waves.append([min(1, D-1)])        # J+1
    if D >= 4:
        waves.append([min(3, D-1)])        # J+3
    if D >= 8:
        waves.append([min(7, D-1)])        # J+7
    if not waves:
        waves = [[0]]
    # Répartir TR uniformément sur ces vagues (avec diffusion autour du jour cible)
    share = review_min // len(waves)
    spill = review_min - share * len(waves)

    def around(day: int) -> List[int]:
        # renvoyer [d-1, d, d+1] borné
        cand = [max(0, day-1), day, min(D-1, day+1)]
        # unique en gardant l'ordre
        seen = set()
        out = []
        for c in cand:
            if c not in seen:
                out.append(c)
                seen.add(c)
        return out

    for i, w in enumerate(waves):
        minutes = share + (1 if i < spill else 0)
        target = w[0]
        order = around(target)
        rem = push("review", minutes, order)
        if rem > 0:
            push("review", rem, days_idx)

    # 4) Mocks: surtout dans le dernier 40% des jours
    order_mock = [d for d in days_idx if d in last_40]
    if not order_mock:
        order_mock = days_idx
    rem = push("mock", mock_min, order_mock)
    if rem > 0:
        push("mock", rem, days_idx[::-1])

    # Respect d'un minimum/jour: si une journée non bloquée est < min, remonter via réalloc légère
    for d in days_idx:
        if d in blocked:
            continue
        day_sum = sum(per_day[d].values())
        if day_sum == 0:
            continue
        if day_sum < mind:
            need = mind - day_sum
            # essayer de « tirer » des jours plus chargés
            for s in reversed(days_idx):
                if s == d:
                    continue
                src_sum = sum(per_day[s].values())
                if src_sum - need >= mind or src_sum > mind + 60:
                    # déplacer depuis review puis exo puis learn
                    for k in ["review", "exo", "learn", "mock"]:
                        move = min(per_day[s][k], need)
                        per_day[s][k] -= move
                        per_day[d][k] += move
                        need -= move
                        if need <= 0:
                            break
                if need <= 0:
                    break

    # Construire la liste finale
    items: List[PlanItem] = []
    for d in days_idx:
        date_str = None
        if start_date:
            date_str = (start_date + dt.timedelta(days=d)).isoformat()
        items.append(PlanItem(
            day_index=d,
            date=date_str,
            learn_min=int(round(per_day[d]["learn"])),
            exercises_min=int(round(per_day[d]["exo"])),
            review_min=int(round(per_day[d]["review"])),
            mock_min=int(round(per_day[d]["mock"])),
        ))
    return items


# =========================
#   Orchestrateur principal
# =========================

def build_study_plan(
    contents: List[ContentBlock],
    exam: ExamProfile,
    user: UserProfile,
    constraints: Constraints,
    start_date: Optional[dt.date] = None,
    want_mocks: bool = True,
    mock_duration_min: int = 90,
    mock_review_ratio: float = 0.5
) -> PlanResult:

    # 1) Temps d'appropriation initiale (TAI)
    TAI = estimate_initial_learning_minutes(contents, user)

    # 2) Temps d’exercices (TEXO)
    TEXO = estimate_exercise_minutes(contents, exam, user)

    # 3) Temps de révision (TR) – courbe de l’oubli
    TR = estimate_review_minutes(TAI, user, constraints.days_available)

    # 4) Examens blancs (TEB)
    TEB = estimate_mock_minutes(constraints.days_available, want_mocks, mock_duration_min, mock_review_ratio)

    # 5) Ajustement selon objectif vs maîtrise : gonfle TR/TEXO si gros écart
    gap = max(0.0, user.target_grade - user.current_mastery)
    if gap > 0.25:
        TEXO = int(round(TEXO * (1.0 + 0.25 * (gap / 0.75))))   # jusqu’à ~+8%
        TR   = int(round(TR   * (1.0 + 0.35 * (gap / 0.75))))   # jusqu’à ~+12%

    # 6) Répartition par jour avec plafonds/fatigue
    schedule = distribute_minutes_over_days(
        learn_min=TAI,
        exo_min=TEXO,
        review_min=TR,
        mock_min=TEB,
        constraints=constraints,
        start_date=start_date
    )

    total = TAI + TEXO + TR + TEB
    return PlanResult(
        total_minutes=total,
        per_day=schedule,
        breakdown={"learn": TAI, "exercises": TEXO, "review": TR, "mock": TEB},
        params_used={
            "target_grade": user.target_grade,
            "current_mastery": user.current_mastery,
            "days_available": constraints.days_available,
            "max_minutes_per_day": constraints.max_minutes_per_day
        }
    )


# =========================
#   Exemple d'utilisation
# =========================

if __name__ == "__main__":
    # Exemple : 3 chapitres de 70 slides (densité normale), 5 jours
    contents = [
        ContentBlock(units=210, unit_type="slide", difficulty=1.05, novelty=1.1, density=1.0)
    ]
    exam = ExamProfile(
        weight_theory=0.4, weight_problems=0.45, weight_memorization=0.15,
        question_mix={"QCM":0.3,"problèmes":0.6,"rédaction":0.1}
    )
    user = UserProfile(
        read_speed_slide_min=1.0,   # 1 min/slide base
        notes_factor=1.15,
        target_grade=0.85,
        current_mastery=0.5
    )
    constraints = Constraints(days_available=5, max_minutes_per_day=240, min_minutes_per_day=60)

    start = dt.date.today()
    plan = build_study_plan(contents, exam, user, constraints, start_date=start,
                            want_mocks=True, mock_duration_min=75, mock_review_ratio=0.6)

    print("=== RÉSUMÉ ===")
    print("Total:", plan.total_minutes, "min (", round(plan.total_minutes/60,1), "h)")
    print("Détails:", plan.breakdown)
    print("Params:", plan.params_used)
    print("\n=== PLAN ===")
    for item in plan.per_day:
        print(
            f"Jour {item.day_index+1} ({item.date}): "
            f"Learn {item.learn_min} min | Exos {item.exercises_min} min | "
            f"Révision {item.review_min} min | Mock {item.mock_min} min"
        )
