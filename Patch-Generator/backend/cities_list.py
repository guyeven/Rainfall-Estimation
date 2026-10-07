# Simple default city list. You can extend this as you like.
CITIES_TEXT = """London:GB
Birmingham:GB
Manchester:GB
Glasgow:GB
Dublin:IE
Belfast:GB
Edinburgh:GB

Paris:FR
Marseille:FR
Lyon:FR
Toulouse:FR
Nice:FR
Nantes:FR
Strasbourg:FR

Berlin:DE
Hamburg:DE
Munich:DE
Cologne:DE
Frankfurt:DE
Stuttgart:DE
Düsseldorf:DE

Madrid:ES
Barcelona:ES
Valencia:ES
Seville:ES

Rome:IT
Milan:IT
Naples:IT
Turin:IT
"""

# Coordinates for a subset of cities (extend if you like)
CITY_COORDS = {
    "London": (51.5074, -0.1278),
    "Birmingham": (52.4862, -1.8904),
    "Manchester": (53.4808, -2.2426),
    "Glasgow": (55.8642, -4.2518),
    "Dublin": (53.3498, -6.2603),
    "Belfast": (54.5970, -5.9301),
    "Edinburgh": (55.9533, -3.1883),
    "Paris": (48.8566, 2.3522),
    "Marseille": (43.2965, 5.3698),
    "Lyon": (45.7640, 4.8357),
    "Toulouse": (43.6047, 1.4442),
    "Nice": (43.7102, 7.2620),
    "Nantes": (47.2184, -1.5536),
    "Strasbourg": (48.5734, 7.7521),
    "Berlin": (52.5200, 13.4050),
    "Hamburg": (53.5511, 9.9937),
    "Munich": (48.1351, 11.5820),
    "Cologne": (50.9375, 6.9603),
    "Frankfurt": (50.1109, 8.6821),
    "Stuttgart": (48.7758, 9.1829),
    "Düsseldorf": (51.2277, 6.7735),
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3851, 2.1734),
    "Valencia": (39.4699, -0.3763),
    "Seville": (37.3891, -5.9845),
    "Rome": (41.9028, 12.4964),
    "Milan": (45.4642, 9.1900),
    "Naples": (40.8518, 14.2681),
    "Turin": (45.0703, 7.6869),
    "Dresden": (51.0504, 13.7373),
    "Leipzig": (51.3397, 12.3731),
    "Amsterdam": (52.3676, 4.9041),
    "Rotterdam": (51.9244, 4.4777),
    "The Hague": (52.0705, 4.3007),
    "Utrecht": (52.0907, 5.1214),
    "Eindhoven": (51.4416, 5.4697),
    "Brussels": (50.8503, 4.3517),
    "Antwerp": (51.2194, 4.4025),
    "Ghent": (51.0543, 3.7174),
    "Liège": (50.6326, 5.5797),
    "Luxembourg City": (49.6116, 6.1319),
    "Vienna": (48.2082, 16.3738),
    "Graz": (47.0707, 15.4395),
    "Linz": (48.3069, 14.2858),
    "Zurich": (47.3769, 8.5417),
    "Geneva": (46.2044, 6.1432),
    "Basel": (47.5596, 7.5886),
    "Lausanne": (46.5197, 6.6323),
    "Copenhagen": (55.6761, 12.5683),
    "Aarhus": (56.1629, 10.2039),
    "Stockholm": (59.3293, 18.0686),
    "Gothenburg": (57.7089, 11.9746),
    "Malmö": (55.6050, 13.0038),
    "Oslo": (59.9139, 10.7522),
    "Bergen": (60.3913, 5.3221),
    "Helsinki": (60.1699, 24.9384),
    "Tampere": (61.4978, 23.7610),
    "Espoo": (60.2055, 24.6559),
    "Sevilla": (37.3891, -5.9845),
    "Zaragoza": (41.6488, -0.8891),
    "Málaga": (36.7213, -4.4214),
    "Bilbao": (43.2630, -2.9350),
    "Lisbon": (38.7223, -9.1393),
    "Porto": (41.1579, -8.6291),
    "Braga": (41.5454, -8.4265),
    "Palermo": (38.1157, 13.3615),
    "Genoa": (44.4056, 8.9463),
    "Bologna": (44.4949, 11.3426),
    "Florence": (43.7696, 11.2558),
    "Athens": (37.9838, 23.7275),
    "Thessaloniki": (40.6401, 22.9444),
    "Warsaw": (52.2297, 21.0122),
    "Kraków": (50.0647, 19.9450),
    "Łódź": (51.7592, 19.4560),
    "Wrocław": (51.1079, 17.0385),
    "Poznań": (52.4064, 16.9252),
    "Gdańsk": (54.3520, 18.6466),
    "Prague": (50.0755, 14.4378),
    "Brno": (49.1951, 16.6068),
    "Budapest": (47.4979, 19.0402),
    "Debrecen": (47.5316, 21.6273),
    "Bucharest": (44.4268, 26.1025),
    "Cluj-Napoca": (46.7712, 23.6236),
    "Sofia": (42.6977, 23.3219),
    "Varna": (43.2141, 27.9147),
    "Belgrade": (44.7866, 20.4489),
    "Novi Sad": (45.2671, 19.8335),
    "Zagreb": (45.8150, 15.9819),
    "Ljubljana": (46.0569, 14.5058),
    "Bratislava": (48.1486, 17.1077),
    "Tallinn": (59.4370, 24.7536),
    "Riga": (56.9496, 24.1052),
    "Vilnius": (54.6872, 25.2797),
}
