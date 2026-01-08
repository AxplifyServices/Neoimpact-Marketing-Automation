from __future__ import annotations

import os
import sqlite3
import streamlit as st

from app.crc.crc_engine import (
    get_next_crc_input_row,
    skip_current_row,
    mark_joignable_succes,
    mark_joignable_sans_succes,
    mark_injoignable,
    call_current_client,
)

# ✅ IMPORTANT: on ne reconstruit plus crc_input / traitement_mail ici
# from app.crc.crc_input_store_sqlite import refresh_crc_input
# from app.traitements.traitement_mail_engine import refresh_and_send_mails

from app.scripts.batch_manuel import run_batch_manuel  # ✅ centralisation dans le batch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# Helpers existants (inchangés)
# =========================
def get_client_display_name(radical_compte: str) -> str:
    if not radical_compte:
        return ""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Nom, Prenom FROM clients WHERE radical_compte = ? LIMIT 1",
            (radical_compte,),
        )
        r = cur.fetchone()
        if not r:
            return radical_compte
        nom = str(r["Nom"] or "").strip()
        prenom = str(r["Prenom"] or "").strip()
        out = (prenom + " " + nom).strip()
        return out if out else radical_compte
    finally:
        conn.close()


def get_variable_cible_from_campaign(id_campagne: str) -> str:
    if not id_campagne:
        return ""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.variable_cible
            FROM campagnes c
            JOIN modeles m ON m.ID_MODELE = c.id_modele
            WHERE c.id_campagne = ?
            """,
            (id_campagne,),
        )
        r = cur.fetchone()
        return str(r[0] or "").strip() if r else ""
    finally:
        conn.close()


def get_contenu_from_campaign_action(id_campagne: str, id_action: str) -> str:
    if not id_campagne or not id_action:
        return ""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.liste_action
            FROM campagnes c
            JOIN modeles m ON m.ID_MODELE = c.id_modele
            WHERE c.id_campagne = ?
            """,
            (id_campagne,),
        )
        r = cur.fetchone()
        if not r:
            return ""
        import json
        s = r[0] or ""
        try:
            actions = json.loads(s) if s else []
        except Exception:
            return ""

        id_action_str = str(id_action or "").strip()
        if not id_action_str:
            return ""

        for a in actions:
            if str(a.get("ID", "")).strip() == id_action_str:
                return str(a.get("Contenu", "") or "")

        return ""
    finally:
        conn.close()


# =========================
# NEW: lecture table action_vers_cc (inchangé)
# =========================
def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def load_actions_vers_cc() -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "action_vers_cc"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM action_vers_cc
            ORDER BY date_affectation DESC, id_campagne DESC, radical_compte DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# =========================
# UI
# =========================
def main():
    st.set_page_config(page_title="CRC", layout="wide")
    st.title("📞 CRC")

    # ✅ Nouveau: le refresh déclenche le batch complet
    if st.button("🔄 Rafraîchir CRM", use_container_width=True):
        try:
            report = run_batch_manuel(verbose=False)
            st.success(
                "Batch OK ✅\n\n"
                f"- campagnes_started: {report.get('campagnes_started', 0)}\n"
                f"- etat_synced: {report.get('etat_synced', 0)}\n"
                f"- canceled_applied: {report.get('canceled_applied', 0)}\n"
                f"- statut_refreshed: {report.get('statut_refreshed', 0)}\n"
                f"- days_refreshed: {report.get('days_refreshed', 0)}\n"
                f"- crc_output_processed: {report.get('crc_output_processed', 0)}\n"
                f"- mail_output_processed: {report.get('mail_output_processed', 0)}\n"
                f"- crc_input_rebuilt: {report.get('crc_input_rebuilt', 0)}\n"
                f"- mail_queue_rebuilt: {report.get('mail_queue_rebuilt', 0)}\n"
                f"- mail_sent_ok: {report.get('mail_sent_ok', 0)}"
            )
        except Exception as e:
            st.error(f"Batch KO: {e}")

        st.rerun()

    # --- Récupérer la première ligne à traiter
    row = get_next_crc_input_row()

    if not row:
        st.info("Aucune ligne à traiter dans crc_input.")
    else:
        rc = str(row.get("Radical_compte", "")).strip()
        id_camp = str(row.get("ID_CAMPAGNE", "")).strip()

        display_name = get_client_display_name(rc)
        variable_cible = get_variable_cible_from_campaign(id_camp)
        statut_actuel = str(row.get("statut_actuel", "") or "").strip()

        contenu_msg = get_contenu_from_campaign_action(id_camp, str(row.get("ID_Action", "") or "").strip())

        top = st.container(border=True)
        with top:
            c1, c2, c3 = st.columns([0.45, 0.35, 0.20], vertical_alignment="center")

            c1.markdown(f"### {display_name}")
            if variable_cible:
                c2.markdown(f"**{variable_cible}** : {statut_actuel}")
            else:
                c2.markdown(f"**Statut actuel** : {statut_actuel}")

            if contenu_msg:
                st.markdown("**Contenu du message :**")
                st.text_area("", value=contenu_msg, height=120, disabled=True, key=f"crc_contenu_{id_camp}_{rc}")
            else:
                st.caption("Contenu du message : (vide)")

            b1, b2, b3, b4, b5 = st.columns([0.16, 0.20, 0.20, 0.16, 0.28], vertical_alignment="center")

            if b1.button("Skip", use_container_width=True):
                skip_current_row(id_camp, rc)
                st.rerun()

            if b2.button("Joignable avec succès", use_container_width=True):
                mark_joignable_succes(row)
                st.rerun()

            if b3.button("Joignable sans succès", use_container_width=True):
                mark_joignable_sans_succes(row)
                st.rerun()

            if b4.button("Injoignable", use_container_width=True):
                mark_injoignable(row)
                st.rerun()

            if b5.button("📞 Appeler", use_container_width=True):
                resp = call_current_client(row)
                st.info(resp)

    # Optionnel: affichage actions_vers_cc (inchangé)
    st.divider()
    st.subheader("📌 Actions en traitement CC")
    actions_cc = load_actions_vers_cc()
    if actions_cc:
        st.dataframe(actions_cc, use_container_width=True)
    else:
        st.caption("Aucune action CC pour le moment.")


if __name__ == "__main__":
    main()
