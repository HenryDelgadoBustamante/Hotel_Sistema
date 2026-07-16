from django.apps import AppConfig


class ReportesConfig(AppConfig):
    name = 'reportes'

    def ready(self):
        # Import signal handlers to ensure they are registered
        import reportes.signals
