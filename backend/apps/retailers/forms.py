import json

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify
from functools import lru_cache
from pathlib import Path

from apps.retailers.models import Retailer
from apps.stores.models import Store


COUNTRY_DATA_PATH = Path("/usr/share/zoneinfo/iso3166.tab")
COUNTRY_CURRENCY_MAP = {
    "AE": "AED", "AU": "AUD", "BD": "BDT", "BR": "BRL", "CA": "CAD", "CH": "CHF",
    "CN": "CNY", "CZ": "CZK", "DE": "EUR", "DK": "DKK", "EG": "EGP", "ES": "EUR",
    "FR": "EUR", "GB": "GBP", "GR": "EUR", "HK": "HKD", "HU": "HUF", "ID": "IDR",
    "IE": "EUR", "IN": "INR", "IT": "EUR", "JP": "JPY", "KE": "KES", "KR": "KRW",
    "MX": "MXN", "MY": "MYR", "NG": "NGN", "NL": "EUR", "NO": "NOK", "NZ": "NZD",
    "PH": "PHP", "PK": "PKR", "PL": "PLN", "QA": "QAR", "RO": "RON", "SA": "SAR",
    "SE": "SEK", "SG": "SGD", "TH": "THB", "TR": "TRY", "UA": "UAH", "US": "USD",
    "ZA": "ZAR", "BD": "BDT", "AR": "ARS", "CL": "CLP", "CO": "COP", "PE": "PEN",
    "VN": "VND", "TW": "TWD", "IL": "ILS", "AT": "EUR", "BE": "EUR", "FI": "EUR",
    "PT": "EUR", "LU": "EUR", "IE": "EUR", "SI": "EUR", "SK": "EUR", "LT": "EUR",
    "LV": "EUR", "EE": "EUR", "HR": "EUR", "BG": "BGN", "RS": "RSD", "IS": "ISK",
    "KZ": "KZT", "KW": "KWD", "OM": "OMR", "BH": "BHD", "MA": "MAD", "TN": "TND",
}
COUNTRY_DIAL_CODE_MAP = {
    "AE": "+971", "AU": "+61", "BD": "+880", "BR": "+55", "CA": "+1", "CH": "+41",
    "CN": "+86", "DE": "+49", "DK": "+45", "EG": "+20", "ES": "+34", "FR": "+33",
    "GB": "+44", "GR": "+30", "HK": "+852", "HU": "+36", "ID": "+62", "IE": "+353",
    "IN": "+91", "IT": "+39", "JP": "+81", "KE": "+254", "KR": "+82", "MX": "+52",
    "MY": "+60", "NG": "+234", "NL": "+31", "NO": "+47", "NZ": "+64", "PH": "+63",
    "PK": "+92", "PL": "+48", "QA": "+974", "RO": "+40", "SA": "+966", "SE": "+46",
    "SG": "+65", "TH": "+66", "TR": "+90", "UA": "+380", "US": "+1", "ZA": "+27",
    "AR": "+54", "CL": "+56", "CO": "+57", "PE": "+51", "VN": "+84", "TW": "+886",
    "IL": "+972", "AT": "+43", "BE": "+32", "FI": "+358", "PT": "+351", "LU": "+352",
    "SI": "+386", "SK": "+421", "LT": "+370", "LV": "+371", "EE": "+372", "HR": "+385",
    "BG": "+359", "RS": "+381", "IS": "+354", "KZ": "+7", "KW": "+965", "OM": "+968",
    "BH": "+973", "MA": "+212", "TN": "+216",
}
COUNTRY_DIAL_CODE_MAP.update({
    "AD": "+376", "AF": "+93", "AG": "+1-268", "AI": "+1-264", "AL": "+355",
    "AM": "+374", "AO": "+244", "AQ": "+672", "AS": "+1-684", "AW": "+297",
    "AX": "+358", "AZ": "+994", "BA": "+387", "BB": "+1-246", "BF": "+226",
    "BI": "+257", "BJ": "+229", "BL": "+590", "BM": "+1-441", "BN": "+673",
    "BO": "+591", "BQ": "+599", "BS": "+1-242", "BT": "+975", "BV": "+47",
    "BW": "+267", "BY": "+375", "BZ": "+501", "CC": "+61", "CD": "+243",
    "CF": "+236", "CG": "+242", "CI": "+225", "CK": "+682", "CM": "+237",
    "CR": "+506", "CU": "+53", "CV": "+238", "CW": "+599", "CX": "+61", "CZ": "+420",
    "CY": "+357", "DJ": "+253", "DM": "+1-767", "DO": "+1-809", "DZ": "+213",
    "EC": "+593", "EH": "+212", "ER": "+291", "ET": "+251", "FJ": "+679",
    "FK": "+500", "FM": "+691", "FO": "+298", "GA": "+241", "GD": "+1-473",
    "GE": "+995", "GF": "+594", "GG": "+44", "GH": "+233", "GI": "+350",
    "GL": "+299", "GM": "+220", "GN": "+224", "GP": "+590", "GQ": "+240",
    "GS": "+500", "GT": "+502", "GU": "+1-671", "GW": "+245", "GY": "+592",
    "HM": "+672", "HN": "+504", "HT": "+509", "IM": "+44", "IO": "+246",
    "IQ": "+964", "IR": "+98", "JE": "+44", "JM": "+1-876", "JO": "+962",
    "KG": "+996", "KH": "+855", "KI": "+686", "KM": "+269", "KN": "+1-869", "KY": "+1-345",
    "KP": "+850", "LA": "+856", "LB": "+961", "LC": "+1-758", "LI": "+423",
    "LK": "+94", "LR": "+231", "LS": "+266", "LY": "+218", "MC": "+377",
    "MD": "+373", "ME": "+382", "MF": "+590", "MG": "+261", "MH": "+692",
    "MK": "+389", "ML": "+223", "MM": "+95", "MN": "+976", "MO": "+853",
    "MP": "+1-670", "MQ": "+596", "MR": "+222", "MS": "+1-664", "MT": "+356",
    "MU": "+230", "MV": "+960", "MW": "+265", "MZ": "+258", "NA": "+264",
    "NC": "+687", "NE": "+227", "NF": "+672", "NI": "+505", "NP": "+977",
    "NR": "+674", "NU": "+683", "PA": "+507", "PF": "+689", "PG": "+675",
    "PM": "+508", "PN": "+64", "PR": "+1-787", "PS": "+970", "PW": "+680",
    "PY": "+595", "RE": "+262", "RU": "+7", "RW": "+250", "SB": "+677",
    "SC": "+248", "SD": "+249", "SH": "+290", "SJ": "+47", "SL": "+232",
    "SM": "+378", "SN": "+221", "SO": "+252", "SR": "+597", "SS": "+211",
    "ST": "+239", "SV": "+503", "SX": "+1-721", "SY": "+963", "SZ": "+268",
    "TC": "+1-649", "TD": "+235", "TF": "+262", "TG": "+228", "TJ": "+992",
    "TK": "+690", "TL": "+670", "TM": "+993", "TO": "+676", "TT": "+1-868",
    "TV": "+688", "TZ": "+255", "UG": "+256", "UM": "+1", "UY": "+598",
    "UZ": "+998", "VA": "+379", "VC": "+1-784", "VE": "+58", "VG": "+1-284",
    "VI": "+1-340", "VU": "+678", "WF": "+681", "WS": "+685", "XK": "+383",
    "YE": "+967", "YT": "+262", "ZM": "+260", "ZW": "+263",
})
COUNTRY_LOCATION_DEFAULTS = {
    "AE": {"state": "Dubai", "city": "Dubai", "postal_code": "00000"},
    "AU": {"state": "New South Wales", "city": "Sydney", "postal_code": "2000"},
    "BD": {"state": "Dhaka", "city": "Dhaka", "postal_code": "1000"},
    "BR": {"state": "Sao Paulo", "city": "Sao Paulo", "postal_code": "01000-000"},
    "CA": {"state": "Ontario", "city": "Toronto", "postal_code": "M5H 2N2"},
    "CH": {"state": "Zurich", "city": "Zurich", "postal_code": "8000"},
    "CN": {"state": "Beijing", "city": "Beijing", "postal_code": "100000"},
    "DE": {"state": "Berlin", "city": "Berlin", "postal_code": "10115"},
    "DK": {"state": "Capital Region", "city": "Copenhagen", "postal_code": "1050"},
    "EG": {"state": "Cairo Governorate", "city": "Cairo", "postal_code": "11511"},
    "ES": {"state": "Madrid", "city": "Madrid", "postal_code": "28001"},
    "FR": {"state": "Ile-de-France", "city": "Paris", "postal_code": "75001"},
    "GB": {"state": "England", "city": "London", "postal_code": "SW1A 1AA"},
    "GR": {"state": "Attica", "city": "Athens", "postal_code": "10552"},
    "HK": {"state": "Hong Kong", "city": "Hong Kong", "postal_code": ""},
    "ID": {"state": "Jakarta", "city": "Jakarta", "postal_code": "10110"},
    "IE": {"state": "Leinster", "city": "Dublin", "postal_code": "D01"},
    "IN": {"state": "Delhi", "city": "New Delhi", "postal_code": "110001"},
    "IT": {"state": "Lazio", "city": "Rome", "postal_code": "00100"},
    "JP": {"state": "Tokyo", "city": "Tokyo", "postal_code": "100-0001"},
    "KR": {"state": "Seoul", "city": "Seoul", "postal_code": "04524"},
    "KW": {"state": "Kuwait Governorate", "city": "Kuwait City", "postal_code": ""},
    "MY": {"state": "Kuala Lumpur", "city": "Kuala Lumpur", "postal_code": "50000"},
    "NG": {"state": "Lagos", "city": "Lagos", "postal_code": "100001"},
    "NL": {"state": "North Holland", "city": "Amsterdam", "postal_code": "1012"},
    "NO": {"state": "Oslo", "city": "Oslo", "postal_code": "0150"},
    "NZ": {"state": "Auckland", "city": "Auckland", "postal_code": "1010"},
    "PH": {"state": "Metro Manila", "city": "Manila", "postal_code": "1000"},
    "PK": {"state": "Punjab", "city": "Lahore", "postal_code": "54000"},
    "PL": {"state": "Masovia", "city": "Warsaw", "postal_code": "00-001"},
    "QA": {"state": "Doha", "city": "Doha", "postal_code": ""},
    "RO": {"state": "Bucharest", "city": "Bucharest", "postal_code": "010000"},
    "SA": {"state": "Riyadh Province", "city": "Riyadh", "postal_code": "11461"},
    "SE": {"state": "Stockholm", "city": "Stockholm", "postal_code": "111 20"},
    "SG": {"state": "Central Singapore", "city": "Singapore", "postal_code": "018989"},
    "TH": {"state": "Bangkok", "city": "Bangkok", "postal_code": "10200"},
    "TR": {"state": "Istanbul", "city": "Istanbul", "postal_code": "34000"},
    "UA": {"state": "Kyiv", "city": "Kyiv", "postal_code": "01001"},
    "US": {"state": "California", "city": "Los Angeles", "postal_code": "90001"},
    "ZA": {"state": "Gauteng", "city": "Johannesburg", "postal_code": "2000"},
}

INDIA_LOCATION_DATA = {
    "Andaman and Nicobar Islands": {
        "Port Blair": ["744101"],
        "Mayabunder": ["744204"],
        "Diglipur": ["744202"],
    },
    "Andhra Pradesh": {
        "Amaravati": ["522020"],
        "Anantapur": ["515001"],
        "Kadapa": ["516001"],
        "Rajahmundry": ["533101"],
        "Visakhapatnam": ["530001"],
        "Vijayawada": ["520001"],
        "Guntur": ["522002"],
        "Tirupati": ["517501"],
        "Kurnool": ["518001"],
        "Nellore": ["524001"],
    },
    "Arunachal Pradesh": {
        "Itanagar": ["791111"],
        "Naharlagun": ["791110"],
        "Tawang": ["790104"],
    },
    "Assam": {
        "Guwahati": ["781001"],
        "Dibrugarh": ["786001"],
        "Silchar": ["788001"],
        "Jorhat": ["785001"],
        "Tezpur": ["784001"],
        "Tinsukia": ["786125"],
    },
    "Bihar": {
        "Patna": ["800001"],
        "Gaya": ["823001"],
        "Muzaffarpur": ["842001"],
        "Bhagalpur": ["812001"],
        "Darbhanga": ["846004"],
        "Purnia": ["854301"],
    },
    "Chandigarh": {"Chandigarh": ["160017", "160018", "160022"]},
    "Chhattisgarh": {
        "Raipur": ["492001"],
        "Bhilai": ["490001"],
        "Bilaspur": ["495001"],
    },
    "Dadra and Nagar Haveli and Daman and Diu": {
        "Daman": ["396210"],
        "Diu": ["362520"],
        "Silvassa": ["396230"],
    },
    "Delhi": {
        "New Delhi": ["110001"],
        "Central Delhi": ["110002"],
        "South Delhi": ["110017"],
        "Dwarka": ["110075"],
        "Rohini": ["110085"],
    },
    "Goa": {
        "Panaji": ["403001"],
        "Margao": ["403601"],
        "Vasco da Gama": ["403802"],
    },
    "Gujarat": {
        "Ahmedabad": ["380001"],
        "Surat": ["395003"],
        "Vadodara": ["390001"],
        "Rajkot": ["360001"],
        "Gandhinagar": ["382010"],
        "Bhavnagar": ["364001"],
        "Jamnagar": ["361001"],
    },
    "Haryana": {
        "Gurugram": ["122001"],
        "Faridabad": ["121001"],
        "Panipat": ["132103"],
        "Ambala": ["133001"],
        "Hisar": ["125001"],
        "Karnal": ["132001"],
    },
    "Himachal Pradesh": {
        "Shimla": ["171001"],
        "Dharamshala": ["176215"],
        "Mandi": ["175001"],
    },
    "Jammu and Kashmir": {
        "Srinagar": ["190001"],
        "Jammu": ["180001"],
        "Anantnag": ["192101"],
    },
    "Jharkhand": {
        "Ranchi": ["834001"],
        "Jamshedpur": ["831001"],
        "Dhanbad": ["826001"],
    },
    "Karnataka": {
        "Bengaluru": ["560001"],
        "Mysuru": ["570001"],
        "Mangaluru": ["575001"],
        "Hubballi": ["580020"],
        "Belagavi": ["590001"],
        "Davanagere": ["577001"],
        "Kalaburagi": ["585101"],
    },
    "Kerala": {
        "Thiruvananthapuram": ["695001"],
        "Kochi": ["682001"],
        "Kozhikode": ["673001"],
        "Thrissur": ["680001"],
        "Kollam": ["691001"],
        "Kannur": ["670001"],
    },
    "Ladakh": {
        "Leh": ["194101"],
        "Kargil": ["194103"],
    },
    "Lakshadweep": {"Kavaratti": ["682555"]},
    "Madhya Pradesh": {
        "Bhopal": ["462001"],
        "Indore": ["452001"],
        "Gwalior": ["474001"],
        "Jabalpur": ["482001"],
        "Ujjain": ["456001"],
        "Sagar": ["470001"],
    },
    "Maharashtra": {
        "Mumbai": ["400001"],
        "Pune": ["411001"],
        "Nagpur": ["440001"],
        "Nashik": ["422001"],
        "Thane": ["400601"],
        "Aurangabad": ["431001"],
        "Solapur": ["413001"],
        "Kolhapur": ["416003"],
    },
    "Manipur": {
        "Imphal": ["795001"],
        "Thoubal": ["795138"],
    },
    "Meghalaya": {
        "Shillong": ["793001"],
        "Tura": ["794001"],
    },
    "Mizoram": {
        "Aizawl": ["796001"],
        "Lunglei": ["796701"],
    },
    "Nagaland": {
        "Kohima": ["797001"],
        "Dimapur": ["797112"],
    },
    "Odisha": {
        "Bhubaneswar": ["751001"],
        "Cuttack": ["753001"],
        "Rourkela": ["769001"],
        "Puri": ["752001"],
        "Sambalpur": ["768001"],
        "Berhampur": ["760001"],
    },
    "Puducherry": {
        "Puducherry": ["605001"],
        "Karaikal": ["609602"],
    },
    "Punjab": {
        "Ludhiana": ["141001"],
        "Amritsar": ["143001"],
        "Jalandhar": ["144001"],
        "Patiala": ["147001"],
        "Bathinda": ["151001"],
        "Mohali": ["160055"],
    },
    "Rajasthan": {
        "Jaipur": ["302001"],
        "Jodhpur": ["342001"],
        "Udaipur": ["313001"],
        "Kota": ["324001"],
        "Ajmer": ["305001"],
        "Bikaner": ["334001"],
    },
    "Sikkim": {
        "Gangtok": ["737101"],
        "Namchi": ["737126"],
    },
    "Tamil Nadu": {
        "Chennai": ["600001"],
        "Coimbatore": ["641001"],
        "Madurai": ["625001"],
        "Tiruchirappalli": ["620001"],
        "Salem": ["636001"],
        "Tiruppur": ["641601"],
        "Erode": ["638001"],
        "Vellore": ["632001"],
    },
    "Telangana": {
        "Hyderabad": ["500001"],
        "Warangal": ["506002"],
        "Nizamabad": ["503001"],
        "Karimnagar": ["505001"],
    },
    "Tripura": {
        "Agartala": ["799001"],
        "Udaipur": ["799120"],
    },
    "Uttar Pradesh": {
        "Lucknow": ["226001"],
        "Kanpur": ["208001"],
        "Varanasi": ["221001"],
        "Noida": ["201301"],
        "Ghaziabad": ["201001"],
        "Agra": ["282001"],
        "Prayagraj": ["211001"],
        "Meerut": ["250001"],
        "Gorakhpur": ["273001"],
    },
    "Uttarakhand": {
        "Dehradun": ["248001"],
        "Haridwar": ["249401"],
        "Haldwani": ["263139"],
    },
    "West Bengal": {
        "Kolkata": ["700001"],
        "Howrah": ["711101"],
        "Siliguri": ["734001"],
        "Durgapur": ["713201"],
        "Asansol": ["713301"],
        "Bardhaman": ["713101"],
        "Kharagpur": ["721301"],
        "Malda": ["732101"],
    },
}

COUNTRY_LOCATION_DETAILS = {
    "US": {
        "California": {"Los Angeles": ["90001"], "San Francisco": ["94102"], "San Diego": ["92101"]},
        "New York": {"New York": ["10001"], "Buffalo": ["14201"], "Albany": ["12207"]},
        "Texas": {"Houston": ["77001"], "Dallas": ["75201"], "Austin": ["73301"]},
        "Florida": {"Miami": ["33101"], "Orlando": ["32801"], "Tampa": ["33601"]},
        "Illinois": {"Chicago": ["60601"], "Springfield": ["62701"]},
    },
    "GB": {
        "England": {"London": ["SW1A 1AA"], "Manchester": ["M1"], "Birmingham": ["B1"]},
        "Scotland": {"Edinburgh": ["EH1"], "Glasgow": ["G1"]},
        "Wales": {"Cardiff": ["CF10"], "Swansea": ["SA1"]},
        "Northern Ireland": {"Belfast": ["BT1"]},
    },
    "CA": {
        "Ontario": {"Toronto": ["M5H"], "Ottawa": ["K1A"], "Mississauga": ["L5B"]},
        "Quebec": {"Montreal": ["H1A"], "Quebec City": ["G1A"]},
        "British Columbia": {"Vancouver": ["V5K"], "Victoria": ["V8W"]},
        "Alberta": {"Calgary": ["T2P"], "Edmonton": ["T5J"]},
    },
    "AU": {
        "New South Wales": {"Sydney": ["2000"], "Newcastle": ["2300"]},
        "Victoria": {"Melbourne": ["3000"], "Geelong": ["3220"]},
        "Queensland": {"Brisbane": ["4000"], "Gold Coast": ["4217"]},
        "Western Australia": {"Perth": ["6000"]},
    },
    "DE": {
        "Berlin": {"Berlin": ["10115"]},
        "Bavaria": {"Munich": ["80331"], "Nuremberg": ["90402"]},
        "North Rhine-Westphalia": {"Cologne": ["50667"], "Dusseldorf": ["40210"]},
        "Hesse": {"Frankfurt": ["60311"]},
    },
    "FR": {
        "Ile-de-France": {"Paris": ["75001"], "Versailles": ["78000"]},
        "Auvergne-Rhone-Alpes": {"Lyon": ["69001"], "Grenoble": ["38000"]},
        "Provence-Alpes-Cote d'Azur": {"Marseille": ["13001"], "Nice": ["06000"]},
    },
    "IT": {
        "Lazio": {"Rome": ["00100"]},
        "Lombardy": {"Milan": ["20100"], "Bergamo": ["24121"]},
        "Campania": {"Naples": ["80100"]},
        "Piedmont": {"Turin": ["10100"]},
    },
    "ES": {
        "Madrid": {"Madrid": ["28001"]},
        "Catalonia": {"Barcelona": ["08001"]},
        "Andalusia": {"Seville": ["41001"], "Malaga": ["29001"]},
        "Valencian Community": {"Valencia": ["46001"]},
    },
    "BD": {
        "Dhaka": {"Dhaka": ["1000"], "Gazipur": ["1700"], "Narayanganj": ["1400"]},
        "Chattogram": {"Chattogram": ["4000"], "Cox's Bazar": ["4700"]},
        "Sylhet": {"Sylhet": ["3100"]},
        "Khulna": {"Khulna": ["9000"]},
    },
    "PK": {
        "Punjab": {"Lahore": ["54000"], "Faisalabad": ["38000"], "Rawalpindi": ["46000"]},
        "Sindh": {"Karachi": ["74000"], "Hyderabad": ["71000"]},
        "Khyber Pakhtunkhwa": {"Peshawar": ["25000"]},
        "Islamabad Capital Territory": {"Islamabad": ["44000"]},
    },
    "AE": {
        "Dubai": {"Dubai": ["00000"]},
        "Abu Dhabi": {"Abu Dhabi": ["00000"], "Al Ain": ["00000"]},
        "Sharjah": {"Sharjah": ["00000"]},
    },
    "SA": {
        "Riyadh Province": {"Riyadh": ["11461"]},
        "Makkah Province": {"Jeddah": ["21442"], "Mecca": ["24231"]},
        "Eastern Province": {"Dammam": ["31411"]},
    },
    "SG": {"Central Singapore": {"Singapore": ["018989"]}},
    "MY": {
        "Kuala Lumpur": {"Kuala Lumpur": ["50000"]},
        "Selangor": {"Shah Alam": ["40000"], "Petaling Jaya": ["46000"]},
        "Penang": {"George Town": ["10000"]},
    },
    "ID": {
        "Jakarta": {"Jakarta": ["10110"]},
        "West Java": {"Bandung": ["40111"]},
        "East Java": {"Surabaya": ["60111"]},
        "Bali": {"Denpasar": ["80227"]},
    },
    "JP": {
        "Tokyo": {"Tokyo": ["100-0001"]},
        "Osaka": {"Osaka": ["530-0001"]},
        "Kanagawa": {"Yokohama": ["220-0001"]},
        "Aichi": {"Nagoya": ["450-0001"]},
    },
    "CN": {
        "Beijing": {"Beijing": ["100000"]},
        "Shanghai": {"Shanghai": ["200000"]},
        "Guangdong": {"Guangzhou": ["510000"], "Shenzhen": ["518000"]},
    },
    "BR": {
        "Sao Paulo": {"Sao Paulo": ["01000-000"], "Campinas": ["13010-000"]},
        "Rio de Janeiro": {"Rio de Janeiro": ["20000-000"]},
        "Minas Gerais": {"Belo Horizonte": ["30000-000"]},
    },
}


@lru_cache(maxsize=1)
def load_country_choices():
    countries = []
    if COUNTRY_DATA_PATH.exists():
        with COUNTRY_DATA_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    code, name = line.split("\t", 1)
                except ValueError:
                    continue
                code = code.strip().upper()
                name = name.strip()
                if len(code) != 2:
                    continue
                countries.append((code, name))
    else:
        countries = [
            ("US", "United States"),
            ("GB", "United Kingdom"),
            ("DE", "Germany"),
            ("IN", "India"),
            ("BD", "Bangladesh"),
        ]
    countries.sort(key=lambda item: item[1].lower())
    choices = [("", "Select Country")]
    choices.extend((code, f"{name} ({code})") for code, name in countries)
    meta = {
        code: {
            "code": code,
            "name": name,
            "currency_code": COUNTRY_CURRENCY_MAP.get(code, "EUR"),
            "dial_code": COUNTRY_DIAL_CODE_MAP.get(code, ""),
        }
        for code, name in countries
    }
    return choices, meta


class RetailerLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "placeholder": "retailer@example.com"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Enter your password"}),
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_superuser or user.global_roles.filter(role__code="super_admin", account_membership__isnull=True).exists():
            raise forms.ValidationError(
                "Wrong retailer details.",
                code="invalid_login",
            )


class RetailerPasswordChangeForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    new_password = forms.CharField(label="New password", strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Create a new password"}))
    repeat_password = forms.CharField(label="Re-enter new password", strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Re-enter the new password"}))

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        from django.contrib.auth.password_validation import validate_password
        validate_password(password, self.user)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") and cleaned.get("repeat_password") and cleaned["new_password"] != cleaned["repeat_password"]:
            self.add_error("repeat_password", "The passwords do not match.")
        return cleaned
        has_retailer_membership = user.account_memberships.filter(
            status="active",
            account__retailer_profile__isnull=False,
        ).exists()
        if not has_retailer_membership:
            raise forms.ValidationError(
                "Wrong retailer details.",
                code="invalid_login",
            )


class RetailerRegistrationForm(forms.Form):
    BUSINESS_TYPE_CHOICES = [
        ("", "Select Business Type..."),
        ("sole_proprietorship", "Sole Proprietorship"),
        ("partnership", "Partnership"),
        ("private_limited", "Private Limited (Pvt Ltd)"),
        ("llc", "Limited Liability Company (LLC)"),
        ("other", "Other"),
    ]

    # Step 1: Basic Info (Required)
    business_name = forms.CharField(max_length=255, label="Business Name", widget=forms.TextInput(attrs={"placeholder": "Enter legal business name"}))
    email = forms.EmailField(label="Business Email", widget=forms.EmailInput(attrs={"placeholder": "you@business.com"}))
    phone_number = forms.CharField(max_length=32, label="Contact Phone Number", widget=forms.TextInput(attrs={"placeholder": "+1 (555) 000-0000"}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Create a secure password"}))
    repeat_password = forms.CharField(label="Repeat Password", strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Confirm your password"}))

    # Step 2: Professional Business details (Optional/Skip-able during onboarding)
    vat_number = forms.CharField(max_length=64, required=False, label="GST / Tax Number (Optional)", widget=forms.TextInput(attrs={"placeholder": "GSTIN / VAT ID"}))
    business_type = forms.ChoiceField(choices=BUSINESS_TYPE_CHOICES, required=False, label="Business Type (Optional)")
    business_address = forms.CharField(required=False, label="Business Address (Optional)", widget=forms.Textarea(attrs={"rows": 2, "placeholder": "123 Business Rd, Suite 100"}))
    business_document = forms.FileField(required=False, label="Business Registration Certificate")
    gst_certificate = forms.FileField(required=False, label="GST / Tax Registration Certificate")
    pan_card = forms.FileField(required=False, label="PAN Card / Tax ID Document")
    cancelled_cheque = forms.FileField(required=False, label="Cancelled Cheque / Bank Statement")
    address_proof = forms.FileField(required=False, label="Address Proof (Utility Bill, Aadhaar, etc.)")
    signature = forms.FileField(required=False, label="Authorized Signatory Signature")
    msme_certificate = forms.FileField(required=False, label="MSME / Udyam Registration (if applicable)")
    fssai_license = forms.FileField(required=False, label="FSSAI License (if food products)")

    DOCUMENT_FIELDS = (
        "business_document", "gst_certificate", "pan_card", "cancelled_cheque",
        "address_proof", "signature", "msme_certificate", "fssai_license",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Titles and required state are deliberately read from the same records
        # used by the retailer-facing template, so admin changes are consistent.
        from apps.retailers.models import SellerVerificationDocumentSetting, SellerVerificationPageSetting
        page_visible = SellerVerificationPageSetting.objects.filter(
            singleton_key="registration", is_active=True, is_visible=True
        ).exists()
        settings = SellerVerificationDocumentSetting.objects.filter(
            is_active=True, field_name__in=self.DOCUMENT_FIELDS
        )
        for setting in settings:
            field = self.fields.get(setting.field_name)
            if field:
                field.label = setting.title
                field.help_text = setting.description
                # A hidden uploader can never be completed by the retailer.
                field.required = setting.is_required and setting.is_visible and page_visible
        for setting in settings:
            if setting.field_name not in self.fields:
                self.fields[setting.field_name] = forms.FileField(
                    required=setting.is_required and setting.is_visible and page_visible,
                    label=setting.title,
                    help_text=setting.description,
                )
        from apps.retailers.models import RetailerRegistrationFieldSetting
        for setting in RetailerRegistrationFieldSetting.objects.filter(is_active=True):
            required = setting.is_required and setting.is_visible
            if setting.field_type == setting.FIELD_SELECT:
                field = forms.ChoiceField(choices=[("", setting.placeholder or "Select...")] + setting.choices_list, required=required, label=setting.title)
            elif setting.field_type == setting.FIELD_TEXTAREA:
                field = forms.CharField(required=required, label=setting.title, widget=forms.Textarea(attrs={"rows": 2, "placeholder": setting.placeholder}))
            else:
                field = forms.CharField(required=required, label=setting.title, widget=forms.TextInput(attrs={"placeholder": setting.placeholder}))
            if setting.field_name in self.fields:
                self.fields[setting.field_name].label = setting.title
                self.fields[setting.field_name].required = required
                self.fields[setting.field_name].widget.attrs["placeholder"] = setting.placeholder
                if setting.field_type == setting.FIELD_SELECT:
                    self.fields[setting.field_name].choices = [("", setting.placeholder or "Select...")] + setting.choices_list
            else:
                self.fields[setting.field_name] = field

    def clean_email(self):
        email = self.cleaned_data.get("email").strip().lower()
        from apps.users.models import User
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        repeat_password = cleaned_data.get("repeat_password")
        if password and repeat_password and password != repeat_password:
            self.add_error("repeat_password", "Passwords do not match.")
        return cleaned_data



class RetailerProfileForm(forms.ModelForm):
    # Hidden library ID fields for media library selector
    business_document_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    gst_certificate_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    pan_card_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    cancelled_cheque_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    address_proof_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    signature_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    msme_certificate_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    fssai_license_library_id = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Retailer
        fields = [
            "legal_name",
            "display_name",
            "vat_number",
            "registration_number",
            "business_type",
            "business_document",
            "gst_certificate",
            "pan_card",
            "cancelled_cheque",
            "address_proof",
            "signature",
            "msme_certificate",
            "fssai_license",
            "support_email",
            "support_phone",
            "business_address",
            "description",
        ]

    # Document fields that use media library selector
    DOCUMENT_FIELDS = [
        "business_document",
        "gst_certificate",
        "pan_card",
        "cancelled_cheque",
        "address_proof",
        "signature",
        "msme_certificate",
        "fssai_license",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.retailers.models import SellerVerificationDocumentSetting
        document_settings = SellerVerificationDocumentSetting.objects.filter(is_active=True)
        for setting in document_settings:
            if setting.field_name in self.fields:
                self.fields[setting.field_name].label = setting.title
                self.fields[setting.field_name].help_text = setting.description
        from apps.retailers.models import RetailerRegistrationFieldSetting
        registration_settings = RetailerRegistrationFieldSetting.objects.filter(is_active=True)
        controlled_fields = {"vat_number", "business_type", "business_address"}
        for setting in registration_settings:
            # Admin visibility is authoritative on both registration and the
            # retailer Business Profile page.
            if setting.field_name in controlled_fields and not setting.is_visible:
                self.fields.pop(setting.field_name, None)
                continue

            required = setting.is_required and setting.is_visible
            if setting.field_name in self.fields:
                old_field = self.fields[setting.field_name]
                if setting.field_type == setting.FIELD_SELECT:
                    field = forms.ChoiceField(
                        choices=[("", setting.placeholder or "Select...")] + setting.choices_list,
                        required=required,
                        label=setting.title,
                    )
                elif setting.field_type == setting.FIELD_TEXTAREA:
                    field = forms.CharField(
                        required=required,
                        label=setting.title,
                        widget=forms.Textarea(attrs={"rows": 2, "placeholder": setting.placeholder}),
                    )
                else:
                    field = forms.CharField(
                        required=required,
                        label=setting.title,
                        widget=forms.TextInput(attrs={"placeholder": setting.placeholder}),
                    )
                field.initial = old_field.initial
                self.fields[setting.field_name] = field
            elif setting.is_visible:
                if setting.field_type == setting.FIELD_SELECT:
                    self.fields[setting.field_name] = forms.ChoiceField(
                        choices=[("", setting.placeholder or "Select...")] + setting.choices_list,
                        required=required,
                        label=setting.title,
                    )
                elif setting.field_type == setting.FIELD_TEXTAREA:
                    self.fields[setting.field_name] = forms.CharField(
                        required=required,
                        label=setting.title,
                        widget=forms.Textarea(attrs={"rows": 2, "placeholder": setting.placeholder}),
                    )
                else:
                    self.fields[setting.field_name] = forms.CharField(
                        required=required,
                        label=setting.title,
                        widget=forms.TextInput(attrs={"placeholder": setting.placeholder}),
                    )
        for setting in document_settings:
            if setting.field_name not in self.fields:
                self.fields[setting.field_name] = forms.FileField(required=setting.is_required and setting.is_visible, label=setting.title, help_text=setting.description)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                pass
            else:
                field.widget.attrs["class"] = "ra-input"

    def save(self, commit=True):
        retailer = super().save(commit=False)
        from apps.catalog.models import MediaLibrary

        for doc_field in self.DOCUMENT_FIELDS:
            lib_id = self.cleaned_data.get(f"{doc_field}_library_id")
            if lib_id:
                asset = MediaLibrary.objects.filter(id=lib_id).first()
                if asset and asset.file:
                    setattr(retailer, doc_field, asset.file)

        if commit:
            retailer.save()
            from apps.retailers.models import SellerVerificationDocumentSetting, SellerVerificationDocumentUpload
            for setting in SellerVerificationDocumentSetting.objects.filter(is_active=True, is_visible=True):
                uploaded = self.cleaned_data.get(setting.field_name)
                if uploaded and setting.field_name not in self.DOCUMENT_FIELDS:
                    SellerVerificationDocumentUpload.objects.update_or_create(
                        retailer=retailer, setting=setting, defaults={"file": uploaded}
                    )
            from apps.retailers.models import RetailerRegistrationFieldSetting
            custom_data = dict(retailer.custom_registration_data or {})
            for setting in RetailerRegistrationFieldSetting.objects.filter(is_active=True, is_system=False):
                if setting.field_name in self.cleaned_data:
                    custom_data[setting.field_name] = self.cleaned_data.get(setting.field_name) or ""
            retailer.custom_registration_data = custom_data
            retailer.save(update_fields=["custom_registration_data", "updated_at"])
        return retailer




class StoreForm(forms.ModelForm):
    logo_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    banner_library_id = forms.CharField(required=False, widget=forms.HiddenInput())
    store_page_sections_payload = forms.CharField(required=False, widget=forms.HiddenInput())

    CURRENCY_CHOICES = [
        ("USD", "USD ($)"),
        ("EUR", "EUR (€)"),
        ("GBP", "GBP (£)"),
        ("INR", "INR (₹)"),
        ("AUD", "AUD (A$)"),
        ("CAD", "CAD (C$)"),
        ("JPY", "JPY (¥)"),
        ("CNY", "CNY (¥)"),
        ("BDT", "BDT (৳)"),
        ("SGD", "SGD (S$)"),
        ("AED", "AED (د.إ)"),
    ]
    currency_code = forms.ChoiceField(choices=CURRENCY_CHOICES, initial="EUR")
    country_code = forms.ChoiceField(choices=load_country_choices()[0], label="Country")
    state = forms.CharField(max_length=120, required=False)
    city = forms.CharField(max_length=120, required=False)
    postal_code = forms.CharField(max_length=32, required=False)
    status = forms.ChoiceField(
        label="Store status",
        choices=((Store.STATUS_DRAFT, "Draft"), (Store.STATUS_ACTIVE, "Active")),
        initial=Store.STATUS_DRAFT,
    )
    slug = forms.SlugField(
        required=False,
        label="Public URL slug",
        help_text="Leave blank to generate it from the store name. You can also enter a custom URL slug.",
    )
    
    class Meta:
        model = Store
        exclude = ("retailer", "status", "is_active", "created_at", "updated_at", "icon", "store_page_sections")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.country_choices, self.country_meta = load_country_choices()
        self.fields["country_code"].choices = self.country_choices
        self.fields["country_code"].widget.attrs.update(
            {
                "class": "ra-input ra-country-select",
                "data-country-select": "true",
            }
        )
        self.fields["country_code"].label = "Country"
        self.fields["currency_code"].widget.attrs["class"] = "ra-input ra-currency-select"
        self.fields["currency_code"].widget.attrs["data-currency-select"] = "true"
        if not self.is_bound:
            initial_code = (self.initial.get("country_code") or getattr(self.instance, "country_code", "") or "").upper()
            if initial_code and initial_code in self.country_meta and not self.initial.get("currency_code"):
                self.fields["currency_code"].initial = self.country_meta[initial_code]["currency_code"]
        self.country_meta_json = self.country_meta
        self.country_location_defaults_json = self._country_location_payload()
        self._configure_location_choice_fields()
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            if field_name not in {"country_code", "currency_code"}:
                field.widget.attrs.setdefault("class", "ra-input")
        if "store_page_tagline" in self.fields:
            self.fields["store_page_tagline"].widget.attrs.setdefault("placeholder", "Example: Inspired living for every home")
        if "store_page_announcement" in self.fields:
            self.fields["store_page_announcement"].widget.attrs.setdefault("placeholder", "Example: Save more on refrigerators, ACs, and washing machines")
        self.store_page_sections_json = self._normalize_store_page_sections(getattr(self.instance, "store_page_sections", None))
        self._prefill_store_channel_defaults()
        if getattr(self.instance, "pk", None) and getattr(self.instance, "status", None) in {Store.STATUS_DRAFT, Store.STATUS_ACTIVE}:
            self.fields["status"].initial = self.instance.status

    def save(self, commit=True):
        store = super().save(commit=False)
        store.status = self.cleaned_data.get("status", Store.STATUS_DRAFT)
        store.is_active = store.status == Store.STATUS_ACTIVE
        if commit:
            store.save()
        return store

    def _prefill_store_channel_defaults(self):
        if self.is_bound or not getattr(self.instance, "pk", None) or not getattr(self.instance, "retailer_id", None):
            return
        fallback = (
            Store.objects.filter(retailer_id=self.instance.retailer_id)
            .exclude(pk=self.instance.pk)
            .order_by("-is_active", "-updated_at", "-created_at")
            .first()
        )
        if not fallback:
            return
        fields = [
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "website_url",
            "facebook_url",
            "instagram_url",
            "linkedin_url",
            "x_url",
            "youtube_url",
            "contact_email",
            "contact_phone",
            "contact_whatsapp",
        ]
        for field_name in fields:
            if field_name in self.fields and not getattr(self.instance, field_name, "") and getattr(fallback, field_name, ""):
                self.fields[field_name].initial = getattr(fallback, field_name)
                self.initial[field_name] = getattr(fallback, field_name)
        if "rating" in self.fields and not getattr(self.instance, "rating", None) and getattr(fallback, "rating", None):
            self.fields["rating"].initial = fallback.rating
        if "average_delivery_days" in self.fields and not getattr(self.instance, "average_delivery_days", None) and getattr(fallback, "average_delivery_days", None):
            self.fields["average_delivery_days"].initial = fallback.average_delivery_days

    def clean_country_code(self):
        code = (self.cleaned_data.get("country_code") or "").strip().upper()
        if code and code not in self.country_meta:
            raise forms.ValidationError("Select a valid country.")
        return code

    def clean_slug(self):
        value = slugify((self.cleaned_data.get("slug") or "").strip())
        if value and Store.objects.filter(slug=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This URL slug is already used by another store.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        country_code = (cleaned_data.get("country_code") or "").upper()
        if country_code:
            default_currency = self.country_meta.get(country_code, {}).get("currency_code")
            if default_currency and not cleaned_data.get("currency_code"):
                cleaned_data["currency_code"] = default_currency
        return cleaned_data

    def clean_store_page_sections_payload(self):
        payload = self.cleaned_data.get("store_page_sections_payload") or "[]"
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Store page sections are not valid JSON.") from exc
        return self._normalize_store_page_sections(parsed)

    def _normalize_store_page_sections(self, sections):
        if not isinstance(sections, list):
            return []
        normalized = []
        allowed_types = {"hero", "image_banner", "image_pair", "tile_grid", "promo_band", "product_shelf", "category_feature"}
        def normalize_fit(value):
            fit = (value or "cover").strip().lower()
            if fit in {"contain", "cover", "fill", "none", "scale-down"}:
                return fit
            if fit in {"auto", "actual"}:
                return "contain"
            if fit in {"100% 100%", "stretch"}:
                return "fill"
            return "cover"

        for index, section in enumerate(sections[:12]):
            if not isinstance(section, dict):
                continue
            section_type = (section.get("type") or "").strip()
            if section_type not in allowed_types:
                continue
            item = {
                "type": section_type,
                "title": (section.get("title") or "").strip()[:160],
                "subtitle": (section.get("subtitle") or "").strip()[:260],
                "deleted_at": (section.get("deleted_at") or "").strip()[:40],
                "image_url": (section.get("image_url") or "").strip()[:500],
                "image_url_2": (section.get("image_url_2") or "").strip()[:500],
                "image_size": (section.get("image_size") or "standard").strip()[:40],
                "image_width": (section.get("image_width") or "").strip()[:40],
                "image_height": (section.get("image_height") or "").strip()[:40],
                "image_fit": normalize_fit(section.get("image_fit")),
                "image_position": (section.get("image_position") or "center").strip()[:80],
                "cta_label": (section.get("cta_label") or "").strip()[:80],
                "cta_url": (section.get("cta_url") or "").strip()[:500],
                "category_slug": (section.get("category_slug") or "").strip()[:160],
                "product_slugs": (section.get("product_slugs") or "").strip()[:700],
                "sort_order": index,
            }
            tiles = section.get("tiles") if isinstance(section.get("tiles"), list) else []
            item["tiles"] = [
                {
                    "title": (tile.get("title") or "").strip()[:120],
                    "subtitle": (tile.get("subtitle") or "").strip()[:180],
                    "image_url": (tile.get("image_url") or "").strip()[:500],
                    "image_size": (tile.get("image_size") or "standard").strip()[:40],
                    "image_width": (tile.get("image_width") or "").strip()[:40],
                    "image_height": (tile.get("image_height") or "").strip()[:40],
                    "image_fit": normalize_fit(tile.get("image_fit")),
                    "image_position": (tile.get("image_position") or "center").strip()[:80],
                    "url": (tile.get("url") or "").strip()[:500],
                }
                for tile in tiles[:6]
                if isinstance(tile, dict) and ((tile.get("title") or "").strip() or (tile.get("image_url") or "").strip())
            ]
            if item["title"] or item["subtitle"] or item["image_url"] or item["image_url_2"] or item["tiles"] or item["category_slug"] or item["product_slugs"]:
                normalized.append(item)
        return normalized

    def _country_location_payload(self):
        payload = {code: dict(defaults) for code, defaults in COUNTRY_LOCATION_DEFAULTS.items()}
        for code, meta in self.country_meta.items():
            fallback_name = meta.get("name") or code
            payload.setdefault(
                code,
                {
                    "state": fallback_name,
                    "city": fallback_name,
                    "postal_code": "00000",
                    "freeform": True,
                },
            )
            payload[code].setdefault("labels", self._location_labels_for_country(code))
            payload[code].setdefault("visibility", self._location_visibility_for_country(code))
        for code, state_map in COUNTRY_LOCATION_DETAILS.items():
            if code in payload:
                default_state = next(iter(state_map.keys()), payload[code].get("state", ""))
                default_city = next(iter(state_map.get(default_state, {}).keys()), payload[code].get("city", ""))
                default_postal = next(iter(state_map.get(default_state, {}).get(default_city, []) or []), payload[code].get("postal_code", ""))
                payload[code].update({
                    "state": payload[code].get("state") or default_state,
                    "city": payload[code].get("city") or default_city,
                    "postal_code": payload[code].get("postal_code") or default_postal,
                    "states": list(state_map.keys()),
                    "cities_by_state": {
                        state: list(cities.keys())
                        for state, cities in state_map.items()
                    },
                    "postal_codes_by_city": {
                        city: pincodes
                        for cities in state_map.values()
                        for city, pincodes in cities.items()
                    },
                })
        payload["IN"] = {
            "state": "Delhi",
            "city": "New Delhi",
            "postal_code": "110001",
            "labels": self._location_labels_for_country("IN"),
            "visibility": self._location_visibility_for_country("IN"),
            "states": list(INDIA_LOCATION_DATA.keys()),
            "cities_by_state": {
                state: list(cities.keys())
                for state, cities in INDIA_LOCATION_DATA.items()
            },
            "postal_codes_by_city": {
                city: pincodes
                for cities in INDIA_LOCATION_DATA.values()
                for city, pincodes in cities.items()
            },
        }
        return payload

    def _location_labels_for_country(self, country_code):
        country_code = (country_code or "").upper()
        label_map = {
            "AE": {"state": "Emirate", "city": "City", "postal_code": "Postal Code"},
            "AU": {"state": "State / Territory", "city": "Suburb / City", "postal_code": "Postcode"},
            "BD": {"state": "Division", "city": "City / District", "postal_code": "Postal Code"},
            "BR": {"state": "State", "city": "City", "postal_code": "CEP"},
            "CA": {"state": "Province / Territory", "city": "City", "postal_code": "Postal Code"},
            "CN": {"state": "Province / Municipality", "city": "City", "postal_code": "Postal Code"},
            "DE": {"state": "Federal State", "city": "City", "postal_code": "Postal Code"},
            "ES": {"state": "Autonomous Community", "city": "City", "postal_code": "Postal Code"},
            "FR": {"state": "Region", "city": "City", "postal_code": "Postal Code"},
            "GB": {"state": "Region / County", "city": "Town / City", "postal_code": "Postcode"},
            "HK": {"state": "Region", "city": "District", "postal_code": "Postal Code"},
            "IN": {"state": "State / Union Territory", "city": "City", "postal_code": "PIN Code"},
            "IT": {"state": "Region", "city": "City", "postal_code": "CAP / Postal Code"},
            "JP": {"state": "Prefecture", "city": "City / Ward", "postal_code": "Postal Code"},
            "MY": {"state": "State / Federal Territory", "city": "City", "postal_code": "Postcode"},
            "PK": {"state": "Province / Territory", "city": "City", "postal_code": "Postal Code"},
            "SG": {"state": "Region", "city": "Area", "postal_code": "Postal Code"},
            "US": {"state": "State", "city": "City", "postal_code": "ZIP Code"},
        }
        return label_map.get(country_code, {"state": "State / Province / Region", "city": "City", "postal_code": "Postal Code"})

    def _location_visibility_for_country(self, country_code):
        country_code = (country_code or "").upper()
        return {
            "state": country_code not in {"HK", "SG", "QA", "KW", "BH"},
            "city": True,
            "postal_code": country_code not in {"HK", "QA", "KW"},
        }

    def _location_options_for(self, country_code, state_value="", city_value=""):
        country_code = (country_code or "").upper()

        def as_choices(values, placeholder):
            choices = [("", placeholder)]
            for value in values:
                if value:
                    choices.append((value, value))
            return choices

        detailed_locations = {"IN": INDIA_LOCATION_DATA, **COUNTRY_LOCATION_DETAILS}
        if country_code in detailed_locations:
            state_map = detailed_locations[country_code]
            states = list(state_map.keys())
            selected_state = state_value if state_value in state_map else ""
            if selected_state:
                cities = list(state_map[selected_state].keys())
            else:
                cities = sorted({city for state_cities in state_map.values() for city in state_cities})
            selected_city = city_value if city_value in cities else ""
            if selected_city:
                pincodes = []
                for state_cities in state_map.values():
                    if selected_city in state_cities:
                        pincodes = state_cities[selected_city]
                        break
            else:
                pincodes = sorted({pin for state_cities in state_map.values() for city_pins in state_cities.values() for pin in city_pins})
            return {
                "state": as_choices(states, "Select State"),
                "city": as_choices(cities, "Select City"),
                "postal_code": as_choices(pincodes, "Select Postal Code"),
            }

        defaults = COUNTRY_LOCATION_DEFAULTS.get(country_code, {})
        fallback_name = self.country_meta.get(country_code, {}).get("name") or country_code
        state = defaults.get("state") or fallback_name
        city = defaults.get("city") or fallback_name
        postal = defaults.get("postal_code") or "00000"
        return {
            "state": as_choices([state], "Select State"),
            "city": as_choices([city], "Select City"),
            "postal_code": as_choices([postal], "Select Postal Code"),
        }

    def _configure_location_choice_fields(self):
        for field_name, placeholder in (("state", "Select State"), ("city", "Select City"), ("postal_code", "Select Postal Code")):
            self.fields[field_name].widget.attrs.update(
                {
                    "class": "ra-input ra-location-select",
                    "data-location-field": field_name,
                    "placeholder": placeholder,
                    "autocomplete": "off",
                }
            )

    def save(self, commit=True):
        store = super().save(commit=False)
        from apps.catalog.models import MediaLibrary

        # Keep location data explicit so retailer and admin forms persist the
        # same address fields even when the country-specific UI changes labels
        # or visibility.
        for field_name in (
            "address_line1", "address_line2", "city", "state", "postal_code", "country_code"
        ):
            if field_name in self.cleaned_data:
                setattr(store, field_name, (self.cleaned_data.get(field_name) or "").strip())
        
        logo_id = self.cleaned_data.get("logo_library_id")
        if logo_id:
            asset = MediaLibrary.objects.filter(id=logo_id).first()
            if asset and asset.file:
                store.logo = asset.file
                
        banner_id = self.cleaned_data.get("banner_library_id")
        if banner_id:
            asset = MediaLibrary.objects.filter(id=banner_id).first()
            if asset and asset.file:
                store.banner = asset.file
        store.store_page_sections = self.cleaned_data.get("store_page_sections_payload") or []
                
        if commit:
            store.save()
        return store



class StoreStaffInviteForm(forms.Form):
    ROLE_CHOICES = [
        ("retailer_manager", "Retailer Manager"),
        ("product_manager", "Product Manager"),
        ("stock_manager", "Stock Manager"),
        ("order_manager", "Order Manager"),
        ("finance_manager", "Finance Manager"),
        ("report_viewer", "Report Viewer"),
    ]

    email = forms.EmailField()
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    phone = forms.CharField(required=False)
    title = forms.CharField(required=False)
    role_codes = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Roles",
        help_text="Select one or more roles for this staff member.",
    )
    store = forms.ModelChoiceField(queryset=Store.objects.none())

    def __init__(self, *args, **kwargs):
        store_queryset = kwargs.pop("store_queryset", Store.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["store"].queryset = store_queryset
        ordered_fields = ["email", "title", "first_name", "last_name", "phone", "role_codes", "store"]
        self.order_fields(ordered_fields)
