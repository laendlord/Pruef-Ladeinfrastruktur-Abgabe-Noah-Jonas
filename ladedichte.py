import os                           # Werte auslesen, hier der API Key
import requests                     # Dafür da Daten aus dem Internet abrufen, also die 3 APIs
import pandas as pd                 # Tabellen erstellen
import geopandas as gpd             # Tabellen mit Geodaten erstellen
import matplotlib.pyplot as plt     # Diagramme erstellen
from dotenv import load_dotenv      # Funktion importieren, umv.env-Dateien einzulesen

# EVA: Eingabe (APIs), Verarbeitung (Filtern, Zählen), Ausgabe (Tabelle, Plot)

load_dotenv()                           # liest die Datei .env
ocm_key = os.getenv("OCM_API_KEY")      # API-Key steht NICHT im Code, Key wird in Variable ocm_key gespeichert

# Stadtname -> Gemeindeschlüssel (dict)
# Dictionary haben jeweils einen Key (hier der Stadtname) und einen Value (hier der Gemeindeschlüssel)
staedte = {
    "Berlin": "11000000", "Hamburg": "02000000", "München": "09162000",
    "Köln": "05315000", "Stuttgart": "08111000", "Dresden": "14612000",
    "Erfurt": "16051000", "Heidelberg": "08221000", "Dessau-Roßlau": "15001000",
    "Schweinfurt": "09662000", "Hof": "09464000", "Pirmasens": "07317000"
}

# diese Variable definiert welche Werte in der OpenChargeMap wir nicht als öffentlich werten
privat = ["Private - Restricted Access", "Privately Owned - Notice Required"]



def get_stadt(ags):
    # Grenze, Einwohner und Fläche einer Stadt vom BKG holen
    # vg250-EW ist Name des Datensatzes => "Verwaltungsgebiete im Maßstab 1:250.000 mit Einwohnerwerten"
    url = "https://sgx.geodatenzentrum.de/wfs_vg250-ew"
    # params gleicht einem dictionary
    # WFS ist ein Standard für Geodaten
    # typeNames definiert welche Ebenen wir brauchen (Gemeiden, nicht Kreise oder Länder)
    # srsName definiert in welchem Format der Server die Koordinaten liefern soll (bei uns in Längen & Breitengraden)
    # cql_filter ist ein Filter der nach der Bedingung sucht
    # gf=4 bedeutet "nur die Landfläche" und nicht z.B. die Wasserfläche
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "vg250-ew:vg250_gem", "outputFormat": "application/json",
        "srsName": "EPSG:4326", "cql_filter": "ags='" + ags + "' AND gf=4"
    }
    # Request.get ruft die URL ab und baut mit params=params eine lange URL => dadurch landen wir richtig
    # ungefähr so sieht die Ausgabe von response aus
    #    {
    # "type": "FeatureCollection",
    # "features": [
    #    {
    #    "type": "Feature",
    #    "geometry": {
    #        "type": "MultiPolygon",
    #        "coordinates": [[[[11.36, 48.16], [11.37, 48.17], ... , [11.36, 48.16]]]]
    #    },
    #    "properties": {
    #        "ags": "09162000",
    #        "gen": "München",
    #        "ewz": 1505005,
    #        "kfl": 310.7,
    #        "gf": 4,
    #        ...
    #    }
    #    }
    #]
    #}
    response = requests.get(url, params=params, timeout=60)
    # Zeile macht viel auf einmal, man liest sie von innen nach außen
    # "features" greift auf den Eintrag "features zu", darin steckt Liste der gefunden Gemeinden => fester Begriff
    # gpd.GeoDataFram.from_features baut aus dieser Info eine Geo-Tabelle (Tabelle mit zusätzlich zu den normalen Spalten noch eine Spalte
    # mit der Form (der Grenze) hat)
    # .iloc[0] nimmt die erste Zeile dieser Tabelle. Denn gpd hat eine einzeilige Tabelle erstellt
    zeile = gpd.GeoDataFrame.from_features(response.json()["features"]).iloc[0]
    # "geometry" definiert die Stadtgrenze als Vieleck
    # "kfl" ist die Katasterfläche in km2
    return zeile["geometry"], zeile["ewz"], zeile["kfl"]


def get_ocm(grenze):
    # alle Ladestationen im Rechteck um die Stadt
    # grenze.bounds ist eine feststehende Eigenschaft (kommt aus Geopandas) und gibt einem die vier äußersten Punkte
    west, sued, ost, nord = grenze.bounds
    # v3/poi ist der Kartenteil für die API bzgl. Ladestationen
    url = "https://api.openchargemap.io/v3/poi"
    url += "?countrycode=DE"
    # OCM erwartet die Eingabe in einer festen Reihenfolge: Von oben links nach unten rechts
    url += "&boundingbox=({},{}),({},{})".format(nord, west, sued, ost)
    # compact=false sorgt für vollständige Angaben anstatt Abkürzung mit Zahlen o.Ä.
    # verbose=false bedeutet "leere Felder weglassen"
    url += "&maxresults=5000&compact=false&verbose=false"
    url += "&key=" + ocm_key
    response = requests.get(url, timeout=60)
    # Hier wird die vollständige Liste mit allen stationen (als dictionary) geschickt => eine Station ist der Standort einer Ladesäule und kann mehrere Ladepunkte haben
        # Beispiel für eine Station (vereinfacht, nur die Felder, die wir nutzen):
    # {
    #     "ID": 123456,
    #     "AddressInfo": {"Latitude": 49.4093, "Longitude": 8.6942},
    #     "NumberOfPoints": 4,
    #     "Connections": [
    #         {"Quantity": 2, "PowerKW": 22},
    #         {"Quantity": 2, "PowerKW": 150}
    #     ],
    #     "UsageType": {"Title": "Public"},
    #     "StatusType": {"IsOperational": True}
    # }
    return response.json()


def anzahl_ladepunkte(station):
    # Hier lesen wir die Anzahl der Ladepunkte aus, wenn das nicht auf Anhieb klappt, haben wir zwei andere Lösungen
    # Regel: NumberOfPoints, sonst Summe der Quantity, sonst 1
    # "NumberOfPoints" ist ein feststehender Begriff
    # Wir prüfen also "gibt" es dieses Feld überhaupt und wenn ja: steht da ein brauchbarer Wert
    # Dieser wird ggf. ausgeben
    if "NumberOfPoints" in station and station["NumberOfPoints"]:
        return station["NumberOfPoints"]
    # station.get("Connections") statt station["Connections"]: Fehlt das Feld, würde die Variante mit eckigen Klammern abstürzen. .get liefert ggf. none
    # or [] sagt "ist das Ergebnis None, nimm stattdessen eine leere Liste"
    # Über None kann python nämlich nicht laufen, über eine leere Liste allerdings schon
    # Konkret bedeutet das also: Gibt es keinen Eintrag zu "Connections", läuft die for-Schleife über die leere Liste und damit 0 Mal
    # => D.h. sie wird direkt übersprungen, aber das Programm stürzt eben nicht ab
    summe = 0
    for anschluss in station.get("Connections") or []:
        if anschluss.get("Quantity"):
            summe += anschluss["Quantity"]
    if summe > 0:
        return summe
    # Backup-Plan für den Backup-Plan, wenn zweimal nichts gefunden wird, sagen wir 1
    return 1


def max_leistung(station):
    # höchste Leistung in kW, None wenn unbekannt
    leistungen = []
    for anschluss in station.get("Connections") or []:
        if anschluss.get("PowerKW"):
            leistungen.append(anschluss["PowerKW"])
    # Das brauchen wir weil OCM nciht vollständig gepflegt ist und das Programm nicht abstürzen darf, wenn die Leistung fehlt
    if len(leistungen) == 0:
        return None
    return max(leistungen)


def get_register(grenze):
    # Ladepunkte im Ladesäulenregister, seitenweise je 2000 Einträge
    west, sued, ost, nord = grenze.bounds
    # FeatureServer = Art des Dienstes: liefert Objekte mit Daten, ähnlich wie WFS. Ein MapServer würde dagegen fertige Kartenbilder liefern
    # 0 = Nummer der Ebene
    # query = Aktion "Abfrage"
    # query sagt der Website "gib mir die Daten", ansonsten bekämen wir Info ÜBER die Daten, nicht die Daten selbst
    url = ("https://services2.arcgis.com/jUpNdisbWqRpMo35/arcgis/rest/services/"
           "Ladesaeulen_in_Deutschland/FeatureServer/0/query")
    eintraege = []
    versatz = 0
    while True:  # Endlosschleife, Ende per break
        # "where": "1=1" ist ein Trick: Arcis will immer einen Filter und diese Bedingung ist immer wahr
        # Dieser Filter bezieht sich auf den Inhalt der Spalten auf der Website
        # "geometryType": "esriGeometryEnvelope" Sagt dem Server, was für eine Form die vier Zahlen beschreiben.
        # Envelope (Hülle) ist bei Esri das Wort für ein Rechteck. Man könnte auch einen Punkt oder ein Vieleck schicken, dann sähe geometry anders aus.
        # "inSR": 4326 ist das gleiche wie EPSG:4326 => definiert die Art der Koordinaten
        # "spatialRel": "esriSpatialRelIntersects" = Spatial Relation, also räumliche Beziehung: Welche Einträge zählen als „im Rechteck“? 
        # Intersects heißt „schneidet“: alles, was das Rechteck berührt oder darin liegt. Bei Punkten wie Ladesäulen heißt das einfach: alles im Rechteck, einschließlich des Rands.
        # "outFields": "Anzahl_Ladepunkte,Status" = Nur diese zwei Spalten mitschicken
        # "orderByFields": "OBJECTID" => Brauchen wir um zu sotieren, später überspringen wir 2000, dann müssen es auch immer die gleichen 2000 sein
        # resultOffset = wie viele Einträge übersprungen werden
        # resultRecordCount = maximale Einträge pro Abfrage
        # f: json = Format
        params = {
            "where": "1=1", "geometry": "{},{},{},{}".format(west, sued, ost, nord),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outSR": 4326,
            "outFields": "Anzahl_Ladepunkte,Status", "orderByFields": "OBJECTID",
            "resultOffset": versatz, "resultRecordCount": 2000, "f": "json"
        }
        # die request liefert ein feature-dictionary mit den Ladesäulen-Einträgen, ungefähr so
        # {
        # "features": [
            # {"geometry": {"x": 8.69, "y": 49.41}, "attributes": {"Anzahl_Ladepunkte": 2, "Status": "In Betrieb"}},
            # {"geometry": {"x": 8.70, "y": 49.40}, "attributes": {"Anzahl_Ladepunkte": 4, "Status": "In Betrieb"}},
            # ... bis zu 2.000 solcher Einträge ...
            # ],
            # "exceededTransferLimit": true         nur vorhanden, wenn es noch mehr gibt
            # }
        daten = requests.get(url, params=params, timeout=60).json()
        for f in daten["features"]:
            # eintraege kommt von oben, haben wir ganz am Anfang definiert
            eintraege.append([f["geometry"]["x"], f["geometry"]["y"], f["attributes"]["Anzahl_Ladepunkte"], f["attributes"]["Status"]])
        if not daten.get("exceededTransferLimit"):
            break
        versatz += len(daten["features"])
    # Wir legen eine Tabelle an, die den Inhalt von Eintraegen hat => Columns sind nach der Reihenfolge bei Eintraege benannt
    df = pd.DataFrame(eintraege, columns=["lon", "lat", "ladepunkte", "status"])
    # Wir laden den Dataframe und die jeweilige Stadtgrenze in die Funktion und überschreiben damit den Original-Df
    df = nur_in_stadt(df, grenze)
    df = df[df["status"] == "In Betrieb"]
    return df["ladepunkte"].sum()


def nur_in_stadt(df, grenze): 
    # nur Punkte behalten, die innerhalb der echten Stadtgrenze liegen
    # points_from_xy macht aus x und y werten punkte mit welchen gpd rechnen kann
    # def lon ist x wert (Ost-West), lat y wert (Nord-Süd) also Koordinaten
    punkte = gpd.points_from_xy(df["lon"], df["lat"])   # x = Länge, y = Breite
    # within selbsterklärend
    # durch die eckige klammer bleiben nur true werte in der tabelle, alles innerhalb der stadtgrenze
    return df[punkte.within(grenze)]


ergebnis = [] # start der hauptschleife (wird außerhalb der schleife nicht geleehrt)
# verweist auf dic. .items() liefert datenpaar 
# diese werden auf stadt, und ags als var verteilt
for stadt, ags in staedte.items():
    print("Bearbeite", stadt)
    # Tupel-Zuweisung
    grenze, einwohner, flaeche = get_stadt(ags)

    # OCM-Rohdaten in eine Tabelle umbauen
    zeilen = []
    # schränkt den abgefragten bereich ein
    for station in get_ocm(grenze):
        # AddressInfo ist der OCM-Schlüssel für alle Angaben zum Ort
        info = station["AddressInfo"]
        # setzt am anfang die nutzung auf none damit es nicht undefiniert ist (None für wissen wir nicht)
        nutzung = None
        # wenn sowohl das "fach" als auch ein entsprechender wert existiert dann geht die schleife weiter
        if "UsageType" in station and station["UsageType"] is not None:
            # hier wird wenn für UsageType Werte vorliegen der nutzungwert von None auf "Titel" geändert
            nutzung = station["UsageType"].get("Title")
        # siehe oben
        in_betrieb = None
        if "StatusType" in station and station["StatusType"] is not None:
            in_betrieb = station["StatusType"].get("IsOperational")
        # append hängt werte der Liste an
        zeilen.append([station["ID"], info["Latitude"], info["Longitude"], anzahl_ladepunkte(station), max_leistung(station), nutzung, in_betrieb])
    # macht aus innerer Liste eine Zeile in df
    df = pd.DataFrame(zeilen, columns=["id", "lat", "lon", "ladepunkte", "max_kw", "nutzung", "in_betrieb"])

    # Verarbeitung: Grenze, Dubletten, privat, außer Betrieb
    df = nur_in_stadt(df, grenze) # aussortieren fon punkten außerhalb der stadt
    df = df.drop_duplicates(subset="id") # entfernt duplikate aus der spalte id
    df = df.sort_values(by="ladepunkte", ascending=False)       # sortiert die liste mit absteigenden Ladepunkten
    # doppelte klammer damit nur die zwei Koordinaten ausgelesen werden
    # round(5) rundet auf fünf nachkommastellen was ungefähr einem m entspricht
    # duplicated prüft ob die koordinaten schon einmal vorkamen
    # ~ kehrt True zu False
    df = df[~df[["lat", "lon"]].round(5).duplicated()]    
    # prüft ob privat enthalten ist   
    df = df[~df["nutzung"].isin(privat)]     
    # prüft ob in_betrieb gegeben ist
    df = df[~df["in_betrieb"].isin([False])]                    

    schnell = pd.to_numeric(df["max_kw"]) > 22 # to_numeric stellt sicher, dass es eine Zahlenspalte ist
    ergebnis.append([stadt, einwohner, flaeche, len(df), df["ladepunkte"].sum(), schnell.sum(), get_register(grenze)])

df = pd.DataFrame(ergebnis, columns=["stadt", "einwohner", "flaeche_km2", "standorte", "ladepunkte", "schnell", "register"])

# die vier Kennzahlen, ganze Spalten auf einmal 
df["pro_km2"] = df["ladepunkte"] / df["flaeche_km2"]
df["pro_100k_ew"] = df["ladepunkte"] / df["einwohner"] * 100_000
df["schnell_anteil"] = df["schnell"] / df["standorte"] * 100
df["abdeckung"] = df["ladepunkte"] / df["register"] * 100

df.sort_values(by="pro_km2", ascending=False, inplace=True) # sortiert die tabelle nach absteigender dichte(inpace=True ändert die werte direkt ohne neue Tabelle)
with pd.option_context("display.max_columns", 12, "display.width", 200):  # alle Spalten anzeigen
    print(df.round(1)) # rundet auf eine nachkommastelle
print("Abdeckung gesamt: {:.1f} %".format(df["ladepunkte"].sum() / df["register"].sum() * 100)) # prozentualer anteil im vergleich zum register
df.to_csv("kennzahlen.csv", sep=";", decimal=",", index=False) # ausgabe auch als csv ohne index

# Plot Ladedichte pro km2 
df.sort_values(by="pro_km2", inplace=True)
plt.figure()                                         # neues Diagramm beginnen
balken = plt.barh(df["stadt"], df["pro_km2"])        # plt.barh liegende balken, df stadt y df pro_km2 x, sandard ist aufsteigend
plt.bar_label(balken, fmt="{:.1f}", padding=3)         # Wert ans Balkenende schreiben
plt.margins(x=0.1)      # verlängert um 10% über den längsten wert hinaus
plt.title("Ladepunkte pro km² laut Open Charge Map") 
plt.xlabel("Ladepunkte pro km²")
plt.tight_layout() # ordnet alles so das nichts abgeschnitten wird
plt.savefig("diakm2.png", dpi=150) # speichert das Diagram im Projektordner
plt.show()

# Plot Ladedichte pro einwohner 
df.sort_values(by="pro_100k_ew", inplace=True)
plt.figure()                                         # neues Diagramm beginnen
balken = plt.barh(df["stadt"], df["pro_100k_ew"])    # die Balken merken
plt.bar_label(balken, fmt="{:.1f}", padding=3)         # Wert ans Balkenende schreiben
plt.margins(x=0.1)                                   # Platz rechts für die Zahlen
plt.title("Ladepunkte pro 100.000 Einwohner laut Open Charge Map")
plt.xlabel("Ladepunkte pro 100.000 Einwohner")
plt.tight_layout()
plt.savefig("diaein.png", dpi=150)
plt.show()