"""Tests de la réception : les documents à traiter d'un dossier d'entrée."""

from pathlib import Path

from saisie_commandes.reception import receive, shared_names


def test_la_reception_rend_les_pdf_du_dossier_dans_l_ordre_de_leurs_noms(tmp_path):
    (tmp_path / "c.pdf").mkdir()
    for name in ("a.pdf", "B.PDF", "notes.txt", "c.pdf/d.pdf"):
        (tmp_path / name).write_bytes(b"")
    assert [path.name for path in receive(tmp_path)] == ["B.PDF", "a.pdf"]


def test_deux_documents_qui_ne_different_que_par_l_extension_partagent_leur_nom():
    documents = [Path("lot/A.pdf"), Path("lot/B.pdf"), Path("lot/A.PDF"), Path("lot/C.Pdf")]
    assert shared_names([*documents, Path("lot/C.pdf")]) == ["A", "C"]
