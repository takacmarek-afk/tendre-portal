import posli_osobny_email as p


def test_kopia_len_kolegovia_z_domeny_bez_clenstva():
    komu, kopia = p.adresati(["Erik@firma.sk"], [("erik@firma.sk", True), ("jana@firma.sk", False),
                                                 ("cudzi@ina.sk", False), ("clen@firma.sk", True)])
    assert komu == ["erik@firma.sk"] and kopia == ["jana@firma.sk"]


def test_sablona_a_sprava():
    predmet, text = p.nacitaj_sablonu("po_skuske")
    assert predmet == "PredTendrom – pokračovanie po skúške" and "240 €" in text and "Marek Takáč" in text
    m = p.zostav(["a@b.sk"], ["c@b.sk"], predmet, text, "r@x.sk")
    assert m["Cc"] == "c@b.sk" and m["Reply-To"] == "r@x.sk" and "List-Unsubscribe" not in m
