from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core import mail
from utilisateur.tasks import send_email_async
from orders.tasks import relancer_paniers_abandonnes_task, generer_facture_async


class CeleryTasksTestCase(TestCase):
    def test_send_email_async_plain(self):
        """Teste l'envoi asynchrone d'un email texte simple via Celery."""
        result = send_email_async(
            subject="Test Sujet",
            message="Contenu de test",
            recipient_list=["client@example.com"],
        )
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Test Sujet")
        self.assertEqual(mail.outbox[0].to, ["client@example.com"])

    def test_send_email_async_html(self):
        """Teste l'envoi asynchrone d'un email HTML via Celery."""
        result = send_email_async(
            subject="Test HTML",
            message="Texte brut fallback",
            recipient_list=["client2@example.com"],
            html_message="<h1>Bonjour</h1>",
        )
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Test HTML")
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")

    def test_generer_facture_async_inexistante(self):
        """Teste que la tâche gère proprement un ID de commande inexistant."""
        result = generer_facture_async(999999)
        self.assertIsNone(result)

    def test_relancer_paniers_abandonnes_vide(self):
        """Teste que la tâche s'exécute sans erreur même s'il n'y a aucun panier abandonné."""
        count = relancer_paniers_abandonnes_task()
        self.assertEqual(count, 0)
