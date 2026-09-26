S_D_M        für alle Auslosungen    S für single, D für doubles, M für mixed doubles
class            für alle Auslosungen    M1 (2;3) für men 1 (2;3), W1 (2;3) für women 1 (2;3),  X1 (2;3) für mixed 1 (2;3)
seeding    nur für Vorrunde    Hier muss die Setzziffer (aus dem Input) eingetragen werden. Höherer Wert = stärker (z. B. 1000 = bester Spieler); eine klassische Setzziffer (1 = bester) muss vorher umgedreht werden. In den Zeilen für Hauptrunde/Consolation bleibt die Spalte leer: die Setzziffer wird aus der Vorrunden-Zeile desselben Spielers/Paares übernommen, die deshalb vorhanden sein muss.
group_no    für alle Auslosungen    Gruppennummer des Spielers/Paares in der Vorrunde (bei Vorrunde: Output; beim Rest: aus dem Input)
group_pos    für alle Auslosungen    Ergebnis-Platz des Spielers/Paares in der Vorrunde (Einzel: im Normalfall 1 bis 6; Doppel/Mixed: im Normalfall 1 bis 4; bei Vorrunde: Output; beim Rest: aus dem Input)
for_main_round    Input: 1 für Hauptrunde, sonst leer oder 0. Output: True in Hauptrunden-Zeilen, False in Consolation-Zeilen, leer in Vorrunden-Zeilen
for_consolation    Input: 1 für Consolation, sonst leer oder 0. Output: True in Consolation-Zeilen, False in Hauptrunden-Zeilen, leer in Vorrunden-Zeilen
draw_number   für Hauptrunde/Consolation: die Rasterzahl des KO-Feldes, also immer eine Potenz von 2. Beim 16er-Feld also eine Zahl zwischen 1 und 16 (am besten auch in dieser Reihenfolge).
startnumber_A    für alle Auslosungen: Schlüsselnummer der players-Datei; im Einzel: Schlüsselnummer des Spielers, im Doppel: Schlüsselnummer des Spielers A; bei einem Freilos leer (siehe is_bye)
last_name_A    für alle Auslosungen: Nachname aus der players-Datei; im Einzel: des Spielers, im Doppel: des Spielers A
country_A    für alle Auslosungen: Land aus der players-Datei; im Einzel: des Spielers, im Doppel: des Spielers A
PPP_chapter_A    für alle Auslosungen: PPP-Stützpunkt aus der players-Datei; im Einzel: des Spielers, im Doppel: des Spielers A
startnumber_B    für Doppel- und Mixed-Auslosungen: Schlüsselnummer des Spielers B aus der players-Datei
last_name_B    für Doppel- und Mixed-Auslosungen: Nachname des Spielers B aus der players-Datei
country_B    für Doppel- und Mixed-Auslosungen: Land des Spielers B aus der players-Datei
PPP_chapter_B    für Doppel- und Mixed-Auslosungen: PPP-Stützpunkt des Spielers B aus der players-Datei
is_bye    für Hauptrunde/Consolation: True, wenn die Position ein Freilos ist (dann sind nur S_D_M, class, for_main_round, for_consolation und draw_number gefüllt), sonst False; in Vorrunden-Zeilen leer
