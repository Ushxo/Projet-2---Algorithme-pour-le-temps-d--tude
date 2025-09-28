from __future__ import annotations
"""
App Bureau (PySide6) pour le planificateur d'étude
---------------------------------------------------
Auteur: Sami Madani
Date: 2025-09-28
Licence: ETS
Version: 1.0
---------------------------------------------------
"""

import sys
import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QMessageBox
)

# === Import du moteur tel quel ===
from study_planner import (
    ContentBlock, ExamProfile, UserProfile, Constraints,
    build_study_plan
)

# ---------- Helpers UI ----------
APP_NAME = "Planificateur d'étude"
ASSETS_DIR = Path("assets")
ICON_PATH = ASSETS_DIR / "icon.png"

DENSITY_HINT = "0.8=aéré • 1.0=normal • 1.2=dense"
LEVEL_HINT = "0.7=facile • 1.0=moyen • 1.3=difficile/nouveau"

UNIT_TYPES = ["page", "slide", "video_min", "exo"]

QSS = """
* { font-family: Inter, Segoe UI, Helvetica, Arial; }
QMainWindow { background: #0f172a; color: #e5e7eb; }
QGroupBox { border: 1px solid #334155; border-radius: 10px; margin-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #93c5fd; }
QLabel { color: #e5e7eb; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit {
  background: #111827; color: #e5e7eb; border: 1px solid #374151; border-radius: 8px; padding: 6px;
}
QPushButton {
  background: #2563eb; color: white; border: 0; border-radius: 10px; padding: 10px 14px; font-weight: 600;
}
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #374151; color: #9ca3af; }
QTableWidget { background: #0b1220; color: #e5e7eb; gridline-color: #334155; }
QHeaderView::section { background: #0b1220; color: #93c5fd; border: 0; border-bottom: 1px solid #334155; padding: 8px; }
QCheckBox { color: #e5e7eb; }
"""

class ContentTable(QTableWidget):
    COLS = ["Type", "Unités", "Difficulté", "Nouveauté", "Densité"]

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLS), parent)
        self.setHorizontalHeaderLabels(self.COLS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setMinimumHeight(160)

    def add_row(self, unit_type="slide", units=70, diff=1.0, nov=1.0, dens=1.0):
        r = self.rowCount()
        self.insertRow(r)
        # Type
        type_cb = QComboBox(); type_cb.addItems(UNIT_TYPES)
        if unit_type in UNIT_TYPES:
            type_cb.setCurrentText(unit_type)
        self.setCellWidget(r, 0, type_cb)
        # Units
        units_sb = QSpinBox(); units_sb.setRange(1, 100000); units_sb.setValue(int(units))
        self.setCellWidget(r, 1, units_sb)
        # Difficulty
        d_ds = QDoubleSpinBox(); d_ds.setRange(0.1, 3.0); d_ds.setSingleStep(0.05); d_ds.setValue(float(diff))
        d_ds.setToolTip(LEVEL_HINT)
        self.setCellWidget(r, 2, d_ds)
        # Novelty
        n_ds = QDoubleSpinBox(); n_ds.setRange(0.1, 3.0); n_ds.setSingleStep(0.05); n_ds.setValue(float(nov))
        n_ds.setToolTip(LEVEL_HINT)
        self.setCellWidget(r, 3, n_ds)
        # Density
        s_ds = QDoubleSpinBox(); s_ds.setRange(0.5, 2.0); s_ds.setSingleStep(0.05); s_ds.setValue(float(dens))
        s_ds.setToolTip(DENSITY_HINT)
        self.setCellWidget(r, 4, s_ds)

    def remove_selected(self):
        rows = sorted({i.row() for i in self.selectedIndexes()}, reverse=True)
        for r in rows:
            self.removeRow(r)

    def to_blocks(self) -> List[ContentBlock]:
        blocks: List[ContentBlock] = []
        for r in range(self.rowCount()):
            unit_type: str = self.cellWidget(r, 0).currentText()
            units: int = self.cellWidget(r, 1).value()
            diff: float = self.cellWidget(r, 2).value()
            nov: float = self.cellWidget(r, 3).value()
            dens: float = self.cellWidget(r, 4).value()
            blocks.append(ContentBlock(units=units, unit_type=unit_type,
                                       difficulty=diff, novelty=nov, density=dens))
        return blocks


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        # Menu (Export)
        export_csv_act = QAction("Exporter en CSV", self)
        export_csv_act.triggered.connect(self.export_csv)
        export_pdf_act = QAction("Exporter en PDF", self)
        export_pdf_act.triggered.connect(self.export_pdf)
        self.menuBar().addAction(export_csv_act)
        self.menuBar().addAction(export_pdf_act)

        # --- Widgets
        root = QWidget(); self.setCentralWidget(root)
        root.setStyleSheet(QSS)
        layout = QVBoxLayout(root)

        # Section Contenu
        gb_content = QGroupBox("Contenu à étudier")
        content_layout = QVBoxLayout(gb_content)
        self.tbl = ContentTable()
        btns = QHBoxLayout()
        add_btn = QPushButton("+ Ajouter un bloc")
        rm_btn = QPushButton("– Supprimer la sélection")
        add_btn.clicked.connect(lambda: self.tbl.add_row())
        rm_btn.clicked.connect(self.tbl.remove_selected)
        btns.addWidget(add_btn); btns.addWidget(rm_btn); btns.addStretch()
        content_layout.addLayout(btns)
        content_layout.addWidget(self.tbl)
        self.tbl.add_row()  # ligne par défaut

        # Section Examen
        gb_exam = QGroupBox("Profil d'examen")
        g1 = QGridLayout(gb_exam)
        self.w_theory = QDoubleSpinBox(); self.w_theory.setRange(0,1); self.w_theory.setValue(0.4)
        self.w_prob   = QDoubleSpinBox(); self.w_prob.setRange(0,1); self.w_prob.setValue(0.4)
        self.w_mem    = QDoubleSpinBox(); self.w_mem.setRange(0,1); self.w_mem.setValue(0.2)
        self.mix_qcm  = QDoubleSpinBox(); self.mix_qcm.setRange(0,1); self.mix_qcm.setValue(0.3)
        self.mix_prob = QDoubleSpinBox(); self.mix_prob.setRange(0,1); self.mix_prob.setValue(0.6)
        self.mix_red  = QDoubleSpinBox(); self.mix_red.setRange(0,1); self.mix_red.setValue(0.1)
        g1.addWidget(QLabel("Poids théorie"), 0,0); g1.addWidget(self.w_theory, 0,1)
        g1.addWidget(QLabel("Poids problèmes"), 0,2); g1.addWidget(self.w_prob, 0,3)
        g1.addWidget(QLabel("Poids mémorisation"), 0,4); g1.addWidget(self.w_mem, 0,5)
        g1.addWidget(QLabel("Mix QCM"), 1,0); g1.addWidget(self.mix_qcm, 1,1)
        g1.addWidget(QLabel("Mix problèmes"), 1,2); g1.addWidget(self.mix_prob, 1,3)
        g1.addWidget(QLabel("Mix rédaction"), 1,4); g1.addWidget(self.mix_red, 1,5)

        # Section Utilisateur
        gb_user = QGroupBox("Profil utilisateur")
        g2 = QGridLayout(gb_user)
        self.v_page = QDoubleSpinBox(); self.v_page.setRange(0.1, 10); self.v_page.setValue(2.5)
        self.v_slide = QDoubleSpinBox(); self.v_slide.setRange(0.1, 10); self.v_slide.setValue(1.0)
        self.v_video = QDoubleSpinBox(); self.v_video.setRange(0.3, 2); self.v_video.setValue(1.0)
        self.notes_factor = QDoubleSpinBox(); self.notes_factor.setRange(1.0, 2.0); self.notes_factor.setSingleStep(0.05); self.notes_factor.setValue(1.15)
        self.lang_penalty = QDoubleSpinBox(); self.lang_penalty.setRange(1.0, 1.5); self.lang_penalty.setSingleStep(0.05); self.lang_penalty.setValue(1.0)
        self.exo_min_each = QDoubleSpinBox(); self.exo_min_each.setRange(1, 60); self.exo_min_each.setValue(7.0)
        self.set_size = QSpinBox(); self.set_size.setRange(1, 200); self.set_size.setValue(12)
        self.retention = QDoubleSpinBox(); self.retention.setRange(0.3, 1.0); self.retention.setSingleStep(0.05); self.retention.setValue(0.6)
        self.target = QDoubleSpinBox(); self.target.setRange(0.5, 1.0); self.target.setSingleStep(0.05); self.target.setValue(0.8)
        self.mastery = QDoubleSpinBox(); self.mastery.setRange(0.0, 1.0); self.mastery.setSingleStep(0.05); self.mastery.setValue(0.5)
        g2_items = [
            ("Lecture (min/page)", self.v_page), ("Lecture (min/slide)", self.v_slide), ("Mult. vidéo", self.v_video),
            ("Prise de notes (×)", self.notes_factor), ("Pénalité langue (×)", self.lang_penalty),
            ("Min/exercice", self.exo_min_each), ("Taille set exos", self.set_size),
            ("Sensibilité à l'oubli", self.retention), ("Objectif (0-1)", self.target), ("Maîtrise actuelle (0-1)", self.mastery)
        ]
        for i, (lbl, w) in enumerate(g2_items):
            r, c = divmod(i, 3)
            g2.addWidget(QLabel(lbl), r, c*2)
            g2.addWidget(w, r, c*2+1)

        # Section Contraintes
        gb_cons = QGroupBox("Contraintes & calendrier")
        g3 = QGridLayout(gb_cons)
        self.days = QSpinBox(); self.days.setRange(1, 365); self.days.setValue(5)
        self.max_day = QSpinBox(); self.max_day.setRange(30, 720); self.max_day.setValue(240)
        self.min_day = QSpinBox(); self.min_day.setRange(0, 720); self.min_day.setValue(60)
        self.start_date = QDateEdit(); self.start_date.setCalendarPopup(True); self.start_date.setDate(QDate.currentDate())
        self.want_mocks = QCheckBox("Inclure des examens blancs")
        self.want_mocks.setChecked(True)
        self.mock_dur = QSpinBox(); self.mock_dur.setRange(30, 300); self.mock_dur.setValue(90)
        self.mock_ratio = QDoubleSpinBox(); self.mock_ratio.setRange(0.0, 1.0); self.mock_ratio.setSingleStep(0.05); self.mock_ratio.setValue(0.5)
        g3_items = [
            ("Jours dispo", self.days), ("Max min/jour", self.max_day), ("Min min/jour", self.min_day),
            ("Date de début", self.start_date), ("", QLabel("")), ("", QLabel("")),
            ("Examens blancs", self.want_mocks), ("Durée mock (min)", self.mock_dur), ("Part correction (0-1)", self.mock_ratio)
        ]
        for i, (lbl, w) in enumerate(g3_items):
            r, c = divmod(i, 3)
            if lbl:
                g3.addWidget(QLabel(lbl), r, c*2)
            g3.addWidget(w, r, c*2 + (0 if lbl == "" else 1))

        # Actions
        actions = QHBoxLayout()
        self.btn_generate = QPushButton("Générer le plan")
        self.btn_generate.clicked.connect(self.generate_plan)
        actions.addStretch(); actions.addWidget(self.btn_generate)

        # Sortie (Résumé + Tableau)
        gb_out = QGroupBox("Résultats")
        out_layout = QVBoxLayout(gb_out)
        self.lbl_summary = QLabel("<i>Le résumé apparaîtra ici.</i>")
        self.tbl_plan = QTableWidget(0, 6)
        self.tbl_plan.setHorizontalHeaderLabels(["Jour", "Date", "Apprentissage", "Exercices", "Révision", "Examens blancs"])
        self.tbl_plan.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_plan.verticalHeader().setVisible(False)
        out_layout.addWidget(self.lbl_summary)
        out_layout.addWidget(self.tbl_plan)

        # Assembler
        layout.addWidget(gb_content)
        layout.addWidget(gb_exam)
        layout.addWidget(gb_user)
        layout.addWidget(gb_cons)
        layout.addLayout(actions)
        layout.addWidget(gb_out)

        # Statut barre
        self.statusBar().showMessage("Prêt")

        self.plan_cache = None  # stocker le dernier résultat pour export

    # ---------- Génération du plan ----------
    def generate_plan(self):
        try:
            blocks = self.tbl.to_blocks()
            if not blocks:
                QMessageBox.warning(self, APP_NAME, "Ajoute au moins un bloc de contenu.")
                return
            # Exam profile
            wt, wp, wm = self.w_theory.value(), self.w_prob.value(), self.w_mem.value()
            total = max(1e-6, wt+wp+wm)
            exam = ExamProfile(
                weight_theory=wt/total, weight_problems=wp/total, weight_memorization=wm/total,
                question_mix={
                    "QCM": self.mix_qcm.value(),
                    "problèmes": self.mix_prob.value(),
                    "rédaction": self.mix_red.value()
                }
            )
            # User profile
            user = UserProfile(
                read_speed_page_min=self.v_page.value(),
                read_speed_slide_min=self.v_slide.value(),
                video_multiplier=self.v_video.value(),
                notes_factor=self.notes_factor.value(),
                language_penalty=self.lang_penalty.value(),
                exercise_min_each=self.exo_min_each.value(),
                problem_set_size=self.set_size.value(),
                retention_sensitivity=self.retention.value(),
                target_grade=self.target.value(),
                current_mastery=self.mastery.value()
            )
            # Constraints
            cons = Constraints(
                days_available=self.days.value(),
                max_minutes_per_day=self.max_day.value(),
                min_minutes_per_day=self.min_day.value(),
                blocked_days=None
            )
            start = self.start_date.date().toPython()
            plan = build_study_plan(
                contents=blocks, exam=exam, user=user, constraints=cons,
                start_date=start, want_mocks=self.want_mocks.isChecked(),
                mock_duration_min=self.mock_dur.value(), mock_review_ratio=self.mock_ratio.value()
            )
            self.plan_cache = plan
            # Résumé
            br = plan.breakdown
            total_h = plan.total_minutes/60
            summary = (
                f"<b>Total :</b> {plan.total_minutes} min (~{total_h:.1f} h)  •  "
                f"<b>Apprentissage :</b> {br['learn']}  •  "
                f"<b>Exercices :</b> {br['exercises']}  •  "
                f"<b>Révision :</b> {br['review']}  •  "
                f"<b>Examens blancs :</b> {br['mock']}"
            )
            self.lbl_summary.setText(summary)
            # Tableau
            self.tbl_plan.setRowCount(0)
            for it in plan.per_day:
                r = self.tbl_plan.rowCount(); self.tbl_plan.insertRow(r)
                self.tbl_plan.setItem(r, 0, QTableWidgetItem(str(it.day_index+1)))
                self.tbl_plan.setItem(r, 1, QTableWidgetItem(it.date or "—"))
                self.tbl_plan.setItem(r, 2, QTableWidgetItem(str(it.learn_min)))
                self.tbl_plan.setItem(r, 3, QTableWidgetItem(str(it.exercises_min)))
                self.tbl_plan.setItem(r, 4, QTableWidgetItem(str(it.review_min)))
                self.tbl_plan.setItem(r, 5, QTableWidgetItem(str(it.mock_min)))
            self.statusBar().showMessage("Plan généré ✔")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Erreur: {e}")

    # ---------- Export CSV ----------
    def export_csv(self):
        if not self.plan_cache:
            QMessageBox.information(self, APP_NAME, "Génère d'abord un plan.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en CSV", "plan.csv", "CSV (*.csv)")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Jour", "Date", "Apprentissage", "Exercices", "Révision", "Examens blancs"]) 
            for it in self.plan_cache.per_day:
                w.writerow([it.day_index+1, it.date or "", it.learn_min, it.exercises_min, it.review_min, it.mock_min])
        self.statusBar().showMessage(f"Exporté: {path}")

    # ---------- Export PDF (simple) ----------
    def export_pdf(self):
        if not self.plan_cache:
            QMessageBox.information(self, APP_NAME, "Génère d'abord un plan.")
            return
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as pdfcanvas
        except Exception:
            QMessageBox.warning(self, APP_NAME, "Installe reportlab : pip install reportlab")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", "plan.pdf", "PDF (*.pdf)")
        if not path: return
        c = pdfcanvas.Canvas(path, pagesize=A4)
        width, height = A4
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, APP_NAME); y -= 22
        br = self.plan_cache.breakdown
        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"Total: {self.plan_cache.total_minutes} min ({self.plan_cache.total_minutes/60:.1f} h)"); y -= 16
        c.drawString(50, y, f"Apprentissage: {br['learn']}  • Exercices: {br['exercises']}  • Révision: {br['review']}  • Examens blancs: {br['mock']}"); y -= 24
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Plan quotidien"); y -= 18
        c.setFont("Helvetica", 10)
        for it in self.plan_cache.per_day:
            line = f"Jour {it.day_index+1} ({it.date or '-'})  |  Apprentissage {it.learn_min}  |  Exercices {it.exercises_min}  |  Révision {it.review_min}  |  Examens blancs {it.mock_min}"
            c.drawString(50, y, line); y -= 14
            if y < 60:
                c.showPage(); y = height - 50
        c.save()
        self.statusBar().showMessage(f"Exporté: {path}")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1100, 850)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
