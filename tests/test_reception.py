"""Tests de la réception : les documents à traiter d'un dossier d'entrée."""

from saisie_commandes.reception import receive


def test_la_reception_rend_les_pdf_du_dossier_dans_l_ordre_de_leurs_noms(tmp_path):
    (tmp_path / "c.pdf").mkdir()
    for name in ("a.pdf", "B.PDF", "notes.txt", "c.pdf/d.pdf"):
        (tmp_path / name).write_bytes(b"")
    assert [path.name for path in receive(tmp_path)] == ["B.PDF", "a.pdf"]
