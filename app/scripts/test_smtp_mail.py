from app.engine.traitement_mail_engine import run_mail_pass, run_mail_meta_loop

if __name__ == "__main__":
    # 1) une seule passe (simple)
    stats = run_mail_pass(limit_rows=50)
    print("=== run_mail_pass ===")
    print(stats)

    # 2) boucle méta (si tu veux tester le chaining mail->mail)
    summary = run_mail_meta_loop(max_passes=10, limit_rows_per_pass=50)
    print("\n=== run_mail_meta_loop ===")
    print("stopped_reason:", summary["stopped_reason"])
    print("passes:", summary["passes"])
    print("total_sent:", summary["total_sent"])
    print("total_failed:", summary["total_failed"])
    print("pass_stats:", summary["pass_stats"])
