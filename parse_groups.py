import re
import json

raw_text = """
👉 [GROUPE 1] : MY Way (Giorgio Armani)
----------------------------------------------------------------------
  • ID #977 : MY Way (Marque: Giorgio Armani)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 90 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: my-way-80768

  • ID #976 : MY Way (Marque: Giorgio Armani)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 30 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: my-way-64568


👉 [GROUPE 2] : la rose bleu (Maison Massimo)
----------------------------------------------------------------------
  • ID #711 : la rose bleu (Marque: Maison Massimo)
    💰 PRIX          : 59 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: rose-bleu-33470

  • ID #710 : la rose bleu (Marque: Maison Massimo)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: rose-bleu-45050


👉 [GROUPE 3] : Terre d'hermès eau givrée (Hermes)
----------------------------------------------------------------------
  • ID #641 : Terre d'hermès eau givrée (Marque: Hermes)
    💰 PRIX          : 139 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 175 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-dherme-eau-givret-39266

  • ID #167 : Terre d'Hermès EAU GIVREE (Marque: Hermès)
    💰 PRIX          : 139 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 175 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: tempete-55935


👉 [GROUPE 4] : Korloff Royal Oud (Korloff Paris)
----------------------------------------------------------------------
  • ID #27 : Korloff Royal Oud (Marque: Korloff Paris)
    💰 PRIX          : 49 900 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 50 en stock | Statut: ACTIF | 88 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: korloff-paris

  • ID #683 : Royal oud (Marque: Korloff)
    💰 PRIX          : 55 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 88 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: royal-oud-63355


👉 [GROUPE 5] : royal oak (Maison Massimo)
----------------------------------------------------------------------
  • ID #708 : royal oak (Marque: Maison Massimo)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: royal-oak-05621

  • ID #709 : royal oak (Marque: Maison Massimo)
    💰 PRIX          : 59 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: royal-oak-78889


👉 [GROUPE 6] : Luxury Velvet Intensely Gold (Sellion Parfums)
----------------------------------------------------------------------
  • ID #181 : Luxury Velvet Intensely Gold (Marque: Sellion Parfums)
    💰 PRIX          : 18 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: oud-wahaaj-55475

  • ID #183 : Luxury Velvet Intensely Blue (Marque: Sellion Parfums)
    💰 PRIX          : 18 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: harmony-code-absolute-90837

  • ID #182 : Luxury Velvet Intensely Brown (Marque: Sellion Parfums)
    💰 PRIX          : 18 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: deux-cent-douze-vip-black-71615


👉 [GROUPE 7] : Sceptre Bronzite (Maison Alhambra)
----------------------------------------------------------------------
  • ID #191 : Sceptre Bronzite (Marque: Maison Alhambra)
    💰 PRIX          : 45 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-065 | Slug: sceptre-oceana-07211

  • ID #65 : Sceptre : Bronzite (Marque: Maison Alhambra / Fragrance World)
    💰 PRIX          : 45 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-FW-SCEPTREBRONZ-039 | Slug: sceptre-bronzite


👉 [GROUPE 8] : Gentleman society SPORT (Givenchy)
----------------------------------------------------------------------
  • ID #604 : Gentleman society SPORT (Marque: Givenchy)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: gentleman-society-sport-16544

  • ID #605 : Gentleman society TEST (Marque: Givenchy)
    💰 PRIX          : 20 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: INACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: gentleman-society-test-94012

  • ID #603 : Gentleman society COF (Marque: Givenchy)
    💰 PRIX          : 20 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: INACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: gentleman-society-cof-52611


👉 [GROUPE 9] : Azzaro Pour Homme (Azzaro)
----------------------------------------------------------------------
  • ID #74 : Azzaro Pour Homme (Marque: Azzaro)
    💰 PRIX          : 72 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: azzaro-pour-homme

  • ID #492 : pour homme (Marque: Azzaro)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: pour-homme-35813

  • ID #490 : pour homme (Marque: Azzaro)
    💰 PRIX          : 65 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: pr-hoe-17578


👉 [GROUPE 10] : NEROLI PORTOFINO (Tom Ford)
----------------------------------------------------------------------
  • ID #872 : NEROLI PORTOFINO (Marque: Tom Ford)
    💰 PRIX          : 199 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: neroli-portofino-86448

  • ID #158 : Tom Ford : Néroli Portofino (Marque: Tom Ford)
    💰 PRIX          : 185 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-dor-lumiere-85687


👉 [GROUPE 11] : Zara : Suprême Vanille (Zara)
----------------------------------------------------------------------
  • ID #172 : Zara : Suprême Vanille (Marque: Zara)
    💰 PRIX          : 25 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: suede-intense-42733

  • ID #89 : Supreme Vanilla (Marque: Zara)
    💰 PRIX          : 25 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-ZA-SUPREMEVANILLA-063 | Slug: supreme-vanilla


👉 [GROUPE 12] : Maître de Blue (Maison Alhambra)
----------------------------------------------------------------------
  • ID #426 : Maître de Blue (Marque: Maison Alhambra)
    💰 PRIX          : 21 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-050 | Slug: maitre-de-blue-34607

  • ID #94 : Maître de Blue (Marque: Maison Alhambra)
    💰 PRIX          : 22 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-FW-MAITREBLUE-068 | Slug: maitre-de-blue


👉 [GROUPE 13] : wanted the Most (Azzaro)
----------------------------------------------------------------------
  • ID #497 : wanted the Most (Marque: Azzaro)
    💰 PRIX          : 710 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: wanted-the-most-92050

  • ID #498 : WANTED  the most (Marque: Azzaro)
    💰 PRIX          : 118 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 9 en stock | Statut: ACTIF | 150 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: wanted-the-most-68534


👉 [GROUPE 14] : Nashein Havict (Genie)
----------------------------------------------------------------------
  • ID #240 : Nashein Havict (Marque: Genie)
    💰 PRIX          : 21 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-119 | Slug: emaan-41759

  • ID #303 : Nashein Havict (Marque: Génie)
    💰 PRIX          : 19 900 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-186 | Slug: nashein-havict-86991


👉 [GROUPE 15] : scandant so nice (Fragrance World)
----------------------------------------------------------------------
  • ID #482 : scandant so nice (Marque: Fragrance World)
    💰 PRIX          : 19 999 FCFA (Prix promo: 17 000 FCFA)
    📦 STOCK & ETAT  : 10 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: scandant-so-nice-64289

  • ID #227 : Scandant So Nice! (Marque: Fragrance World)
    💰 PRIX          : 21 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-104 | Slug: jardin-de-paris-00721


👉 [GROUPE 16] : Éclair (Lattafa)
----------------------------------------------------------------------
  • ID #59 : Éclair (Marque: Lattafa)
    💰 PRIX          : 33 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-LA-ECLAIR-033 | Slug: eclair

  • ID #233 : Eclaire (Marque: Lattafa)
    💰 PRIX          : 35 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-112 | Slug: chogan-millesime-18881


👉 [GROUPE 17] : Sceptre : Malachite (Maison Alhambra)
----------------------------------------------------------------------
  • ID #109 : Sceptre : Malachite (Marque: Maison Alhambra)
    💰 PRIX          : 45 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-MA-MALACHITE-083 | Slug: sceptre-malachite

  • ID #190 : Sceptre Malachite (Marque: Maison Alhambra)
    💰 PRIX          : 45 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: exclusif-tabac-17883


👉 [GROUPE 18] : la petite robe noire AB Test (Guerlain)
----------------------------------------------------------------------
  • ID #988 : la petite robe noire AB Test (Marque: Guerlain)
    💰 PRIX          : 118 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: la-petite-robe-noire-ab-test-55600

  • ID #983 : la petite robe noire N Test (Marque: Guerlain)
    💰 PRIX          : 74 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: INACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: la-petite-robe-noire-n-test-29584


👉 [GROUPE 19] : Invictus (Paco Rabanne)
----------------------------------------------------------------------
  • ID #200 : Invictus (Marque: Paco Rabanne)
    💰 PRIX          : 78 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-076 | Slug: kronos-62221

  • ID #792 : Invictus (Marque: Paco Rabanne)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: invictus-14335


👉 [GROUPE 20] : Des Tentaion (Fragrance World)
----------------------------------------------------------------------
  • ID #111 : Des Tentaion (Marque: Fragrance World)
    💰 PRIX          : 19 900 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: INACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-FW-DESTENTAION-085 | Slug: des-tentaion

  • ID #354 : Des Tentations (Marque: Fragrance World)
    💰 PRIX          : 18 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-244 | Slug: roi-dorient-44648


👉 [GROUPE 21] : Charuto Tobacco Vanille (Paris Corner / Pendora Scents)
----------------------------------------------------------------------
  • ID #126 : Charuto Tobacco Vanille (Marque: Paris Corner / Pendora Scents)
    💰 PRIX          : 24 900 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-PC-CHARUTOVAN-100 | Slug: charuto-tobacco-vanille

  • ID #207 : Charuto Tobacco Vanille (Marque: Pendora Scents)
    💰 PRIX          : 25 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-CSV-083 | Slug: 1-million-le-parfum-69038


👉 [GROUPE 22] : Tom Ford : Fucking Fabulous (Tom Ford)
----------------------------------------------------------------------
  • ID #157 : Tom Ford : Fucking Fabulous (Marque: Tom Ford)
    💰 PRIX          : 245 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: conviction-24666

  • ID #370 : Fucking Fabulous (Marque: Tom Ford (ou Dupe parfait))
    💰 PRIX          : 18 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: expose-intense-55445


👉 [GROUPE 23] : Khair Pistachio (Paris Corner)
----------------------------------------------------------------------
  • ID #55 : Khair Pistachio (Marque: Paris Corner)
    💰 PRIX          : 28 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-PC-KHAIRPIST-029 | Slug: khair-pistache

  • ID #113 : Khair Pistachio (Marque: Paris Corner)
    💰 PRIX          : 25 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-PC-KHAIRPISTACHIO-087 | Slug: khair-pistachio


👉 [GROUPE 24] : la nuit de tresor (Lancome)
----------------------------------------------------------------------
  • ID #1032 : la nuit de tresor (Marque: Lancome)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: la-nuit-de-tresor-03573

  • ID #1033 : la nuit de tresor (Marque: Lancome)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 75 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: la-nuit-de-tresor-47849


👉 [GROUPE 25] : l’ interdit (Givenchy)
----------------------------------------------------------------------
  • ID #967 : l’ interdit (Marque: Givenchy)
    💰 PRIX          : 118 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: l-interdit-78568

  • ID #969 : l’ interdit (Marque: Givenchy)
    💰 PRIX          : 40 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: l-interdit-98348


👉 [GROUPE 26] : Black Oud (Montale)
----------------------------------------------------------------------
  • ID #149 : Black Oud (Marque: Montale)
    💰 PRIX          : 95 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: panther-64550

  • ID #67 : Montale Black Oud (Marque: Montale)
    💰 PRIX          : 98 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-MO-BLACKAOUD-041 | Slug: montale-black-oud

  • ID #738 : black oud (Marque: Montale)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: black-aoud-10631


👉 [GROUPE 27] : Rose Édition Oud (Pascal Morabito)
----------------------------------------------------------------------
  • ID #39 : Rose Édition Oud (Marque: Pascal Morabito)
    💰 PRIX          : 38 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 20 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: PARFUM-PM-ROSEOUD-013 | Slug: rose-edition-oud

  • ID #803 : rose edition oud (Marque: Pascal Morabito)
    💰 PRIX          : 50 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: rose-edition-oud-42050


👉 [GROUPE 28] : ALIVE (Hugo Boss)
----------------------------------------------------------------------
  • ID #1004 : ALIVE (Marque: Hugo Boss)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: INACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: alive-64608

  • ID #1005 : ALIVE (Marque: Hugo Boss)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: alive-21259


👉 [GROUPE 29] : light blue TEST (Dolce Gabana)
----------------------------------------------------------------------
  • ID #957 : light blue TEST (Marque: Dolce Gabana)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: INACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: light-blue-test-60243

  • ID #958 : light blue TEST (Marque: Dolce Gabana)
    💰 PRIX          : 40 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: light-blue-test-82221


👉 [GROUPE 30] : One Million  PARF (Paco Rabanne)
----------------------------------------------------------------------
  • ID #906 : One Million  PARF (Marque: Paco Rabanne)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: one-million-parf-70882

  • ID #784 : One Million  PARFUM (Marque: Paco Rabanne)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: one-million-parf-26864


👉 [GROUPE 31] : Black Opium coff (YSL)
----------------------------------------------------------------------
  • ID #1103 : Black Opium coff (Marque: YSL)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: black-opium-coff-99843

  • ID #1099 : Black Opium COFF (Marque: YSL)
    💰 PRIX          : 114 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 90 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: black-opium-coff-21650


👉 [GROUPE 32] : Etenity (Calvin Klein)
----------------------------------------------------------------------
  • ID #524 : Etenity (Marque: Calvin Klein)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: etenity-37613

  • ID #937 : Eternity (Marque: Calvin Klein)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: eternity-54326


👉 [GROUPE 33] : Ultra Violet (Paco Rabanne)
----------------------------------------------------------------------
  • ID #1073 : Ultra Violet (Marque: Paco Rabanne)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: ultra-violet-14531

  • ID #799 : Ultra Violet (Marque: Paco Rabanne)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: ultra-violet-23079


👉 [GROUPE 34] : Chrome Legend (Azzaro)
----------------------------------------------------------------------
  • ID #488 : Chrome Legend (Marque: Azzaro)
    💰 PRIX          : 69 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 125 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: chrome-legend-05007

  • ID #487 : Chrome Legend (Marque: Azzaro)
    💰 PRIX          : 65 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: chrome-legend-76865


👉 [GROUPE 35] : The Scent (Hugo Boss)
----------------------------------------------------------------------
  • ID #1003 : The Scent (Marque: Hugo Boss)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: the-scent-36106

  • ID #649 : The scent (Marque: Hugo Boss)
    💰 PRIX          : 80 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: the-scent-20463


👉 [GROUPE 36] : Million gold TEST (Paco Rabanne)
----------------------------------------------------------------------
  • ID #1065 : Million gold TEST (Marque: Paco Rabanne)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: INACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: million-gold-test-41264

  • ID #780 : Million gold intense (Marque: Pacco Rabanne)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 90 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: million-gold-intense-95369


👉 [GROUPE 37] : GANYMEDE (Marc Antoine)
----------------------------------------------------------------------
  • ID #719 : GANYMEDE (Marque: Marc Antoine)
    💰 PRIX          : 159 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: ganymede-52398

  • ID #718 : GANYMEDE (Marque: Marc Antoine)
    💰 PRIX          : 199 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: ganymede-56343


👉 [GROUPE 38] : Miake pr homme (L'Eau D'Issey)
----------------------------------------------------------------------
  • ID #690 : Miake pr homme (Marque: L'Eau D'Issey)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 125 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: miake-pr-homme-96625

  • ID #689 : Miake pr homme (Marque: L'Eau D'Issey)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: miake-pr-homme-17766


👉 [GROUPE 39] : HIMALAYAN OUD (Premiere Note)
----------------------------------------------------------------------
  • ID #836 : HIMALAYAN OUD (Marque: Premiere Note)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: himalayan-oud-20670

  • ID #835 : HIMALAYAN OUD T (Marque: Premiere Note)
    💰 PRIX          : 20 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: INACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: himalayan-oud-t-26432


👉 [GROUPE 40] : Terre d'hermes (Hermes)
----------------------------------------------------------------------
  • ID #640 : Terre d'hermes (Marque: Hermes)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-dhermes-89967

  • ID #634 : terre d hermes (Marque: Hermes)
    💰 PRIX          : 159 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 125 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-d-hermes-82062

  • ID #636 : terre d hermes (Marque: Hermes)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 5 en stock | Statut: ACTIF | 75 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-d-hermes-98123

  • ID #635 : Terre d'herme (Marque: Hermes)
    💰 PRIX          : 189 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: terre-dherme-53475


👉 [GROUPE 41] : Million gold GOLD (Paco Rabanne)
----------------------------------------------------------------------
  • ID #1064 : Million gold GOLD (Marque: Paco Rabanne)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 80 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: million-gold-gold-96483

  • ID #782 : million gold OUD (Marque: Paco Rabanne)
    💰 PRIX          : 118 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: million-gold-oud-42016


👉 [GROUPE 42] : Acqua di gio (Giorgeo Armani)
----------------------------------------------------------------------
  • ID #616 : Acqua di gio (Marque: Giorgeo Armani)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: acqua-di-gio-53921

  • ID #617 : Acqua di gio (Marque: Giorgeo Armani)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: acqua-di-gio-84502

  • ID #615 : aqua di gio (Marque: Giorgeo  Amani)
    💰 PRIX          : 129 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 5 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: giorgeo-amani-aqua-di-gio-79000


👉 [GROUPE 43] : Bottled (Hugo Boss)
----------------------------------------------------------------------
  • ID #658 : Bottled (Marque: Hugo Boss)
    💰 PRIX          : 20 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: bottled-48423

  • ID #644 : Bottled (Marque: Hugo Boss)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: bottled-74373

  • ID #643 : Bottled (Marque: Hugo Boss)
    💰 PRIX          : 99 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: bottled-04823


👉 [GROUPE 44] : VOYAGE DE NUIT (Maison Massimo)
----------------------------------------------------------------------
  • ID #714 : VOYAGE DE NUIT (Marque: Maison Massimo)
    💰 PRIX          : 59 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 2 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: voyage-de-nuit-29141

  • ID #715 : VOYAGE DE NUIT (Marque: Maison Massimo)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 3 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: voyage-de-nuit-38081


👉 [GROUPE 45] : Le Male (Jpg)
----------------------------------------------------------------------
  • ID #672 : Le Male (Marque: Jpg)
    💰 PRIX          : 169 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 200 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: le-male-07408

  • ID #671 : Le Male (Marque: Jpg)
    💰 PRIX          : 109 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 4 en stock | Statut: ACTIF | 125 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: le-male-20055


👉 [GROUPE 46] : AMARIGE (Givenchy)
----------------------------------------------------------------------
  • ID #964 : AMARIGE (Marque: Givenchy)
    💰 PRIX          : 89 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 100 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: amarige-91780

  • ID #963 : AMARIGE (Marque: Givenchy)
    💰 PRIX          : 79 000 FCFA (Prix promo: -)
    📦 STOCK & ETAT  : 1 en stock | Statut: ACTIF | 50 ml
    🏷️  SKU & SLUG    : SKU: Aucun | Slug: amarige-82129
"""

groups = []
current_group = None

lines = raw_text.strip().split('\n')
i = 0
while i < len(lines):
    line = lines[i].strip()
    if line.startswith('👉 [GROUPE'):
        # Match group header
        m = re.search(r'\[GROUPE (\d+)\]\s*:\s*(.+?)\s*\((.+?)\)', line)
        if m:
            current_group = {
                'id': int(m.group(1)),
                'titre': m.group(2).strip(),
                'marque_globale': m.group(3).strip(),
                'parfums': []
            }
            groups.append(current_group)
        i += 1
        continue
    
    if line.startswith('• ID #') and current_group is not None:
        # Match perfume line
        m_item = re.search(r'• ID #(\d+)\s*:\s*(.+?)\s*\(Marque:\s*(.+?)\)', line)
        if m_item:
            p_id = int(m_item.group(1))
            p_nom = m_item.group(2).strip()
            p_marque = m_item.group(3).strip()
            
            p_prix = ""
            p_promo = "-"
            p_stock = "0"
            p_statut = "ACTIF"
            p_contenance = ""
            p_sku = "Aucun"
            p_slug = ""
            
            # Read next lines
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith('• ID #') and not lines[j].strip().startswith('👉 [GROUPE'):
                sub = lines[j].strip()
                if '💰 PRIX' in sub:
                    m_p = re.search(r'💰 PRIX\s*:\s*(.+?)\s*\(Prix promo:\s*(.+?)\)', sub)
                    if m_p:
                        p_prix = m_p.group(1).strip()
                        p_promo = m_p.group(2).strip()
                elif '📦 STOCK & ETAT' in sub:
                    m_s = re.search(r'(\d+)\s+en stock\s*\|\s*Statut:\s*(\w+)\s*\|\s*(\d+\s*ml)', sub)
                    if m_s:
                        p_stock = m_s.group(1)
                        p_statut = m_s.group(2)
                        p_contenance = m_s.group(3)
                elif '🏷️  SKU & SLUG' in sub:
                    m_k = re.search(r'SKU:\s*(.+?)\s*\|\s*Slug:\s*(.+)', sub)
                    if m_k:
                        p_sku = m_k.group(1).strip()
                        p_slug = m_k.group(2).strip()
                j += 1
            
            current_group['parfums'].append({
                'id': p_id,
                'nom': p_nom,
                'marque': p_marque,
                'prix': p_prix,
                'promo': p_promo,
                'stock': p_stock,
                'statut': p_statut,
                'contenance': p_contenance,
                'sku': p_sku,
                'slug': p_slug
            })
            i = j - 1
    i += 1

print(f"Parsed {len(groups)} groups with {sum(len(g['parfums']) for g in groups)} items.")

# Now write python generator that creates the HTML
with open('/home/greg/Documents/Accessoire_exclusif/backend/scratch_data.json', 'w', encoding='utf-8') as f:
    json.dump(groups, f, ensure_ascii=False, indent=2)
AMARIGE