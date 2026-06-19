from django.apps import AppConfig

class AtendimentoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'atendimento'

    def ready(self):
        import os
        import time
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_filepath = os.path.join(base_dir, "chrome_console.log")
        try:
            with open(log_filepath, "a", encoding="utf-8") as f:
                f.write(f"\n=========================================\n")
                f.write(f"Django Server Startup: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Log file initialized successfully.\n")
                f.write(f"=========================================\n")
        except Exception as e:
            print(f"Error initializing chrome_console.log: {e}")
