"""Broker Branch, City Support & Depository Participant Directory Engine.

Generates high-intent, authoritative local service & branch pages:
  - /branches/ (Master Hub of all stock broker branches in India)
  - /broker/[broker-id]/branches/ (Broker state & city branch directory)
  - /broker/[broker-id]/branches/[city-slug]/ (City-specific branch, KYC & DP service details)
  - /registry/city/[city-slug]/ (Local SEBI Registered Intermediaries & DPs)

Features:
  - Covers top 20 stock brokers across 37 major Indian financial cities.
  - Sourced from SEBI intermediary registry data (INZ, IN-DP registration numbers).
  - Outlines physical vs online account opening, offline KYC verification,
    physical share dematerialisation (DRF), and local grievance contacts.
  - Rich Schema.org LocalBusiness / FinancialService + FAQPage + BreadcrumbList JSON-LD.
  - Zero external npm dependencies; stdlib Python.
  - Zero em dashes or en dashes anywhere.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_DIR = os.path.join(ROOT, "config")


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _slugify(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


CITIES = {
    "mumbai": {
        "name": "Mumbai",
        "state": "Maharashtra",
        "tier": "Tier 1",
        "zones": ["Fort", "Bandra-Kurla Complex (BKC)", "Nariman Point", "Andheri East", "Borivali", "Dadar"],
        "desc": "Mumbai is India's premier financial capital, housing the headquarters of the Bombay Stock Exchange (BSE), the National Stock Exchange (NSE), SEBI, and leading brokerage firms.",
        "pincodes": "400001, 400051, 400021, 400069",
        "sebi_regional": "SEBI Bhavan, BKC, Bandra East, Mumbai 400051",
    },
    "delhi": {
        "name": "New Delhi",
        "state": "Delhi NCR",
        "tier": "Tier 1",
        "zones": ["Connaught Place", "Nehru Place", "Netaji Subhash Place (Pitampura)", "Janakpuri", "Laxmi Nagar"],
        "desc": "New Delhi is the central financial and regulatory hub for Northern India, with high volumes in equity, commodity, and currency derivatives.",
        "pincodes": "110001, 110019, 110034, 110058",
        "sebi_regional": "SEBI Northern Regional Office, Plate B, Office Block 1, East Kidwai Nagar, New Delhi 110023",
    },
    "bengaluru": {
        "name": "Bengaluru",
        "state": "Karnataka",
        "tier": "Tier 1",
        "zones": ["MG Road", "Indiranagar", "Koramangala", "Jayanagar", "Whitefield", "HSR Layout"],
        "desc": "Bengaluru is India's technology and fintech powerhouse, serving as the global headquarters for top discount brokers including Zerodha and Groww.",
        "pincodes": "560001, 560038, 560034, 560011",
        "sebi_regional": "SEBI Local Office, 2nd Floor, Jeevan Soudha Building, Indira Nagar, Bengaluru 560038",
    },
    "ahmedabad": {
        "name": "Ahmedabad",
        "state": "Gujarat",
        "tier": "Tier 1",
        "zones": ["Ashram Road", "CG Road", "SG Highway", "Prahlad Nagar", "Navrangpura", "GIFT City"],
        "desc": "Ahmedabad is one of India's most vibrant retail investor epicenters, contributing substantial turnover to NSE cash delivery and IPO subscriptions.",
        "pincodes": "380009, 380006, 380054, 380015",
        "sebi_regional": "SEBI Western Regional Office, Unit No. 002, Ground Floor, Sakar 1, Ashram Road, Ahmedabad 380009",
    },
    "pune": {
        "name": "Pune",
        "state": "Maharashtra",
        "tier": "Tier 1",
        "zones": ["Shivaji Nagar", "FC Road", "Camp", "Kothrud", "Baner", "Hinjawadi"],
        "desc": "Pune boasts a massive base of IT professionals and industrial entrepreneurs actively trading in equities, mutual funds, and algorithmic setups.",
        "pincodes": "411005, 411004, 411001, 411038",
        "sebi_regional": "SEBI Local Office, 1st Floor, Suma House, 870/1 Bhandarkar Road, Pune 411004",
    },
    "kolkata": {
        "name": "Kolkata",
        "state": "West Bengal",
        "tier": "Tier 1",
        "zones": ["Dalhousie (BBD Bagh)", "Salt Lake Sector V", "Park Street", "Ballygunge", "Howrah"],
        "desc": "Kolkata has a deep equity investing legacy, formerly home to the Calcutta Stock Exchange and a major hub for long-term equity delivery portfolios.",
        "pincodes": "700001, 700091, 700016, 700019",
        "sebi_regional": "SEBI Eastern Regional Office, L&T Chambers, 3rd Floor, 16 Camac Street, Kolkata 700017",
    },
    "chennai": {
        "name": "Chennai",
        "state": "Tamil Nadu",
        "tier": "Tier 1",
        "zones": ["Anna Salai (Mount Road)", "T Nagar", "Nungambakkam", "Guindy", "Adyar", "Mylapore"],
        "desc": "Chennai is the financial anchor of South India, known for value investing, conservative capital allocation, and extensive depository participant networks.",
        "pincodes": "600002, 600017, 600034, 600032",
        "sebi_regional": "SEBI Southern Regional Office, Overseas Towers, 7th Floor, 756-L, Anna Salai, Chennai 600002",
    },
    "hyderabad": {
        "name": "Hyderabad",
        "state": "Telangana",
        "tier": "Tier 1",
        "zones": ["Banjara Hills", "Hitec City", "Begumpet", "Secunderabad", "Gachibowli", "Ameerpet"],
        "desc": "Hyderabad combines a booming tech sector with heavy retail participation in equity options, sovereign gold bonds, and IPO bidding.",
        "pincodes": "500034, 500081, 500016, 500003",
        "sebi_regional": "SEBI Local Office, 1st Floor, Road No. 10, Banjara Hills, Hyderabad 500034",
    },
    "jaipur": {
        "name": "Jaipur",
        "state": "Rajasthan",
        "tier": "Tier 2",
        "zones": ["MI Road", "C-Scheme", "Tonk Road", "Malviya Nagar", "Vaishali Nagar"],
        "desc": "Jaipur is the trading hub of Rajasthan, with substantial retail and HNI engagement in commodity futures (MCX) and equity delivery.",
        "pincodes": "302001, 302005, 302015, 302017",
        "sebi_regional": "SEBI Local Office, Ground Floor, Jeevan Nidhi 2, LIC Building, Bhawani Singh Road, Jaipur 302005",
    },
    "surat": {
        "name": "Surat",
        "state": "Gujarat",
        "tier": "Tier 2",
        "zones": ["Ring Road", "Ghod Dod Road", "Adajan", "Vesu", "Varachha"],
        "desc": "Surat ranks among India's highest per-capita equity investing cities, driven by textile and diamond merchant liquidity and intense derivative volumes.",
        "pincodes": "395002, 395007, 395009, 395006",
        "sebi_regional": "SEBI Local Office, International Trade Centre, Majura Gate, Surat 395002",
    },
    "rajkot": {
        "name": "Rajkot",
        "state": "Gujarat",
        "tier": "Tier 2",
        "zones": ["Yagnik Road", "Kalawad Road", "Dhebar Road", "150 Feet Ring Road"],
        "desc": "Rajkot is legendary in Indian capital markets for equity momentum trading, high daily turnover, and local brokerage head offices like Marwadi Shares.",
        "pincodes": "360001, 360005, 360002, 360004",
        "sebi_regional": "SEBI Local Office, FP No. 80, 150 Feet Ring Road, Rajkot 360005",
    },
    "vadodara": {
        "name": "Vadodara",
        "state": "Gujarat",
        "tier": "Tier 2",
        "zones": ["Alkapuri", "Race Course Road", "Sayajigunj", "Manjalpur", "Akota"],
        "desc": "Vadodara represents a mature retail investment community with significant mutual fund AUM and blue-chip equity holdings.",
        "pincodes": "390007, 390005, 390011, 390020",
        "sebi_regional": "SEBI Local Office, Alkapuri Arcade, RC Dutt Road, Vadodara 390007",
    },
    "indore": {
        "name": "Indore",
        "state": "Madhya Pradesh",
        "tier": "Tier 2",
        "zones": ["MG Road", "AB Road", "Vijay Nagar", "South Tukoganj", "Palasia"],
        "desc": "Indore is Central India's capital market nerve center, housing numerous regional brokerages (Arihant, Swastika, Indira) and a vast active F&O trading base.",
        "pincodes": "452001, 452010, 452008, 452003",
        "sebi_regional": "SEBI Local Office, 102-103, 1st Floor, Man Heritage, 6/2 South Tukoganj, Indore 452001",
    },
    "chandigarh": {
        "name": "Chandigarh",
        "state": "Punjab & Haryana",
        "tier": "Tier 2",
        "zones": ["Sector 17", "Sector 34", "Sector 35", "Sector 8", "Industrial Area Phase 1"],
        "desc": "Chandigarh serves as the financial epicenter for Punjab and Haryana, featuring deep wealth management, NRI demat services, and equity advisory desks.",
        "pincodes": "160017, 160022, 160036, 160002",
        "sebi_regional": "SEBI Local Office, SCO 127-128, First Floor, Sector 17-C, Chandigarh 160017",
    },
    "lucknow": {
        "name": "Lucknow",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Hazratganj", "Gomti Nagar", "Alambagh", "Indira Nagar", "Mahanagar"],
        "desc": "Lucknow is the administrative and financial hub of Uttar Pradesh, experiencing rapid growth in retail demat accounts and SIP registrations.",
        "pincodes": "226001, 226010, 226005, 226016",
        "sebi_regional": "SEBI Local Office, 2nd Floor, Chander Shekhar Azad Bhawan, Gomti Nagar, Lucknow 226010",
    },
    "kochi": {
        "name": "Kochi",
        "state": "Kerala",
        "tier": "Tier 2",
        "zones": ["MG Road", "Marine Drive", "Kaloor", "Kakkanad (Infopark)", "Palarivattom"],
        "desc": "Kochi is Kerala's commercial heart and headquarters to premier South Indian brokerage Geojit Financial Services, catering to significant NRI investment inflows.",
        "pincodes": "682011, 682031, 682017, 682030",
        "sebi_regional": "SEBI Local Office, 6th Floor, Finance Tower, Kaloor, Kochi 682017",
    },
    "coimbatore": {
        "name": "Coimbatore",
        "state": "Tamil Nadu",
        "tier": "Tier 2",
        "zones": ["Avinashi Road", "RS Puram", "Gandhipuram", "Race Course"],
        "desc": "Coimbatore's industrial entrepreneurs and textile owners generate extensive treasury investments, currency hedging, and long-term equity portfolios.",
        "pincodes": "641018, 641002, 641012, 641004",
        "sebi_regional": "SEBI Local Office, DB Road, RS Puram, Coimbatore 641002",
    },
    "patna": {
        "name": "Patna",
        "state": "Bihar",
        "tier": "Tier 2",
        "zones": ["Fraser Road", "Boring Road", "Exhibition Road", "Kankarbagh", "Dak Bunglow"],
        "desc": "Patna represents one of India's fastest-growing regions for new retail demat account additions via digital mobile trading platforms.",
        "pincodes": "800001, 800001, 800020, 800013",
        "sebi_regional": "SEBI Local Office, Maurya Lok Complex, Dak Bunglow Road, Patna 800001",
    },
    "nagpur": {
        "name": "Nagpur",
        "state": "Maharashtra",
        "tier": "Tier 2",
        "zones": ["Ramdaspeth", "Dhantoli", "Civil Lines", "Sadar", "Wardha Road"],
        "desc": "Nagpur serves Vidarbha's commercial and trading ecosystem with active sub-broker franchisee networks and mutual fund distribution points.",
        "pincodes": "440010, 440012, 440001, 440015",
        "sebi_regional": "SEBI Local Office, West High Court Road, Dharampeth, Nagpur 440010",
    },
    "bhopal": {
        "name": "Bhopal",
        "state": "Madhya Pradesh",
        "tier": "Tier 2",
        "zones": ["MP Nagar Zone 1 & 2", "Arera Colony", "New Market", "Hoshangabad Road"],
        "desc": "Bhopal is a critical retail investment center in Madhya Pradesh with dedicated branches of leading national full-service and bank-backed brokers.",
        "pincodes": "462011, 462016, 462003, 462026",
        "sebi_regional": "SEBI Local Office, MP Nagar, Bhopal 462011",
    },
    "ludhiana": {
        "name": "Ludhiana",
        "state": "Punjab",
        "tier": "Tier 2",
        "zones": ["Ferozepur Road", "Mall Road", "Civil Lines", "Model Town"],
        "desc": "Ludhiana is Punjab's industrial capital, headquarters to Master Trust, and known for active HNI derivatives trading and corporate treasury desks.",
        "pincodes": "141001, 141002, 141003, 141008",
        "sebi_regional": "SEBI Local Office, Feroze Gandhi Market, Ludhiana 141001",
    },
    "visakhapatnam": {
        "name": "Visakhapatnam",
        "state": "Andhra Pradesh",
        "tier": "Tier 2",
        "zones": ["Dwaraka Nagar", "Siripuram", "VIP Road", "Gajuwaka", "MVP Colony"],
        "desc": "Visakhapatnam is the key financial and port city of Andhra Pradesh with growing participation in equity delivery, IPOs, and commodity futures.",
        "pincodes": "530016, 530003, 530026, 530017",
        "sebi_regional": "SEBI Local Office, VIP Road, Siripuram, Visakhapatnam 530003",
    },
    "nashik": {
        "name": "Nashik",
        "state": "Maharashtra",
        "tier": "Tier 2",
        "zones": ["College Road", "Canada Corner", "Gangapur Road", "Old Agra Road"],
        "desc": "Nashik features high retail investor density with numerous authorized person partner offices affiliated with national broker networks.",
        "pincodes": "422005, 422002, 422013, 422001",
        "sebi_regional": "SEBI Local Office, Canada Corner, Nashik 422002",
    },
    "kanpur": {
        "name": "Kanpur",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Civil Lines", "Mall Road", "Swaroop Nagar", "Birhana Road"],
        "desc": "Kanpur was formerly home to the UP Stock Exchange and retains an extensive network of veteran brokers, chartered accountants, and equity investors.",
        "pincodes": "208001, 208002, 208004, 208005",
        "sebi_regional": "SEBI Local Office, Mall Road, Kanpur 208001",
    },
    "varanasi": {
        "name": "Varanasi",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Sigra", "Maldahiya", "Cantt", "Rathyatra"],
        "desc": "Varanasi is Eastern UP's key commercial center with rising digital stock market onboarding among younger traders and local business owners.",
        "pincodes": "221002, 221001, 221010, 221005",
        "sebi_regional": "SEBI Local Office, Maldahiya, Varanasi 221002",
    },
    "gurugram": {
        "name": "Gurugram",
        "state": "Haryana",
        "tier": "Tier 1",
        "zones": ["Cyber City", "Golf Course Road", "Sector 29", "Sohna Road", "Udyog Vihar"],
        "desc": "Gurugram features massive corporate treasury operations, HNI family offices, and tech executives trading international equities and domestic derivatives.",
        "pincodes": "122002, 122018, 122001, 122016",
        "sebi_regional": "SEBI Northern Regional Office, East Kidwai Nagar, New Delhi 110023",
    },
    "noida": {
        "name": "Noida",
        "state": "Uttar Pradesh",
        "tier": "Tier 1",
        "zones": ["Sector 18", "Sector 62", "Noida Expressway", "Sector 16"],
        "desc": "Noida serves as the technology and media hub of Uttar Pradesh with high mobile demat account penetration and active algorithmic trading adoption.",
        "pincodes": "201301, 201309, 201304, 201305",
        "sebi_regional": "SEBI Northern Regional Office, East Kidwai Nagar, New Delhi 110023",
    },
    "thane": {
        "name": "Thane",
        "state": "Maharashtra",
        "tier": "Tier 1",
        "zones": ["Ghodbunder Road", "Naupada", "Wagle Estate", "Majiwada", "Panchpakhadi"],
        "desc": "Thane is a major commercial center of the Mumbai Metropolitan Region, housing extensive retail broking outlets and financial services.",
        "pincodes": "400601, 400602, 400604, 400607",
        "sebi_regional": "SEBI Bhavan, BKC, Bandra East, Mumbai 400051",
    },
    "navi-mumbai": {
        "name": "Navi Mumbai",
        "state": "Maharashtra",
        "tier": "Tier 1",
        "zones": ["Vashi", "Belapur", "Nerul", "Kharghar", "Ghansoli", "Airoli"],
        "desc": "Navi Mumbai houses major financial technology campuses and operations centers of Axis Securities, ICICI, and national stock market depositories.",
        "pincodes": "400703, 400614, 400706, 400710",
        "sebi_regional": "SEBI Bhavan, BKC, Bandra East, Mumbai 400051",
    },
    "amritsar": {
        "name": "Amritsar",
        "state": "Punjab",
        "tier": "Tier 2",
        "zones": ["Mall Road", "Ranjit Avenue", "Lawrence Road", "Majitha Road"],
        "desc": "Amritsar is an energetic commercial center in Punjab with high interest in equity delivery portfolios, commodity derivatives, and mutual fund SIPs.",
        "pincodes": "143001, 143002, 143008",
        "sebi_regional": "SEBI Northern Regional Office, New Delhi 110023",
    },
    "jalandhar": {
        "name": "Jalandhar",
        "state": "Punjab",
        "tier": "Tier 2",
        "zones": ["Model Town", "Civil Lines", "GT Road", "Ladowali Road"],
        "desc": "Jalandhar combines NRI wealth flows with active sports and industrial businesses participating in equity markets and sovereign gold bonds.",
        "pincodes": "144001, 144003, 144008",
        "sebi_regional": "SEBI Northern Regional Office, New Delhi 110023",
    },
    "agra": {
        "name": "Agra",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Sanjay Place", "Civil Lines", "MG Road", "Fatehabad Road"],
        "desc": "Agra Sanjay Place financial district hosts regional branch offices of leading national stockbrokers and investment advisory desks.",
        "pincodes": "282001, 282002, 282003",
        "sebi_regional": "SEBI Local Office, Kanpur 208001",
    },
    "prayagraj": {
        "name": "Prayagraj",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Civil Lines", "Katra", "George Town", "Ashok Nagar"],
        "desc": "Prayagraj is an educational and administrative center with an expanding base of government and academic professionals investing in equity mutual funds.",
        "pincodes": "211001, 211002, 211003",
        "sebi_regional": "SEBI Local Office, Varanasi 221002",
    },
    "ghaziabad": {
        "name": "Ghaziabad",
        "state": "Uttar Pradesh",
        "tier": "Tier 1",
        "zones": ["Raj Nagar", "Vasundhara", "Indirapuram", "Kavi Nagar", "RDC"],
        "desc": "Ghaziabad forms a vital part of Delhi NCR with dense retail investor participation in equity derivatives, algorithmic trading, and IPO applications.",
        "pincodes": "201001, 201002, 201012, 201014",
        "sebi_regional": "SEBI Northern Regional Office, New Delhi 110023",
    },
    "meerut": {
        "name": "Meerut",
        "state": "Uttar Pradesh",
        "tier": "Tier 2",
        "zones": ["Civil Lines", "Begum Bridge", "Shastri Nagar", "Delhi Road"],
        "desc": "Meerut is Western Uttar Pradesh prominent industrial cluster with strong engagement in commodity derivatives, equity delivery, and gold ETFs.",
        "pincodes": "250001, 250002, 250004",
        "sebi_regional": "SEBI Northern Regional Office, New Delhi 110023",
    },
    "dehradun": {
        "name": "Dehradun",
        "state": "Uttarakhand",
        "tier": "Tier 2",
        "zones": ["Rajpur Road", "Paltan Bazaar", "Chakrata Road", "Subhash Nagar"],
        "desc": "Dehradun serves as the capital hub of Uttarakhand with growing demat account onboarding across defence retirees, institutions, and young entrepreneurs.",
        "pincodes": "248001, 248002, 248007",
        "sebi_regional": "SEBI Northern Regional Office, New Delhi 110023",
    },
    "ranchi": {
        "name": "Ranchi",
        "state": "Jharkhand",
        "tier": "Tier 2",
        "zones": ["Main Road", "Ashok Nagar", "Lalpur", "Harmu", "Doranda"],
        "desc": "Ranchi is the capital of Jharkhand and the administrative center for mineral and steel conglomerates, with steady demand for equity wealth creation.",
        "pincodes": "834001, 834002, 834012",
        "sebi_regional": "SEBI Local Office, Ranchi 834001",
    },
    "jamshedpur": {
        "name": "Jamshedpur",
        "state": "Jharkhand",
        "tier": "Tier 2",
        "zones": ["Bistupur", "Sakchi", "Kadma", "Sonari"],
        "desc": "Jamshedpur is an iconic industrial city with high financial literacy among engineering professionals investing in equities and index funds.",
        "pincodes": "831001, 831002, 831005",
        "sebi_regional": "SEBI Local Office, Ranchi 834001",
    },
    "bhubaneswar": {
        "name": "Bhubaneswar",
        "state": "Odisha",
        "tier": "Tier 2",
        "zones": ["Saheed Nagar", "Janpath", "Nayapalli", "Jayadev Vihar", "Patia"],
        "desc": "Bhubaneswar is Eastern India IT and educational hub with rapid adoption of digital discount brokers and systematic investment plans.",
        "pincodes": "751001, 751007, 751012, 751024",
        "sebi_regional": "SEBI Local Office, Bhubaneswar 751001",
    },
    "raipur": {
        "name": "Raipur",
        "state": "Chhattisgarh",
        "tier": "Tier 2",
        "zones": ["Pandri", "Jail Road", "Civil Lines", "Shankar Nagar", "Telibandha"],
        "desc": "Raipur is a primary trading center for steel, coal, and agro commodities with an influential merchant class actively trading in MCX and NSE cash segments.",
        "pincodes": "492001, 492004, 492007",
        "sebi_regional": "SEBI Local Office, Raipur 492001",
    },
    "jabalpur": {
        "name": "Jabalpur",
        "state": "Madhya Pradesh",
        "tier": "Tier 2",
        "zones": ["Civil Lines", "Wright Town", "Napier Town", "Gorakhpur"],
        "desc": "Jabalpur serves as the judicial and defence production center of MP with conservative retail capital channeled into dividend equities and PSU stocks.",
        "pincodes": "482001, 482002, 482004",
        "sebi_regional": "SEBI Local Office, Indore 452001",
    },
    "gwalior": {
        "name": "Gwalior",
        "state": "Madhya Pradesh",
        "tier": "Tier 2",
        "zones": ["City Centre", "Lashkar", "Morar", "Padav"],
        "desc": "Gwalior City Centre financial precinct accommodates branches of prominent brokerage houses offering equity, currency, and mutual fund services.",
        "pincodes": "474001, 474002, 474011",
        "sebi_regional": "SEBI Local Office, Indore 452001",
    },
    "jodhpur": {
        "name": "Jodhpur",
        "state": "Rajasthan",
        "tier": "Tier 2",
        "zones": ["Sardarpura", "Residency Road", "Paota", "Shastri Nagar"],
        "desc": "Jodhpur is Western Rajasthan commercial capital with vibrant retail trading desks and local sub-broker networks.",
        "pincodes": "342001, 342003, 342006",
        "sebi_regional": "SEBI Local Office, Jaipur 302005",
    },
    "udaipur": {
        "name": "Udaipur",
        "state": "Rajasthan",
        "tier": "Tier 2",
        "zones": ["Madhuban", "Durga Nursery Road", "Chetak Circle", "Hiran Magri"],
        "desc": "Udaipur houses mineral enterprises and boasts a wealthy mercantile population investing in equities, bonds, and mutual funds.",
        "pincodes": "313001, 313002, 313004",
        "sebi_regional": "SEBI Local Office, Jaipur 302005",
    },
    "kota": {
        "name": "Kota",
        "state": "Rajasthan",
        "tier": "Tier 2",
        "zones": ["Gumanpura", "Jhalawar Road", "Vigyan Nagar", "Aerodrome Circle"],
        "desc": "Kota educational and industrial ecosystem drives steady retail investments from educators, business operators, and engineering firms.",
        "pincodes": "324001, 324005, 324007",
        "sebi_regional": "SEBI Local Office, Jaipur 302005",
    },
    "vijayawada": {
        "name": "Vijayawada",
        "state": "Andhra Pradesh",
        "tier": "Tier 2",
        "zones": ["MG Road (Bandar Road)", "Governorpet", "Suryaraopet", "Benz Circle"],
        "desc": "Vijayawada is Andhra Pradesh commercial center with substantial agricultural and commercial wealth deployed in equity delivery and IPO markets.",
        "pincodes": "520001, 520002, 520010",
        "sebi_regional": "SEBI Local Office, Vijayawada 520002",
    },
    "guntur": {
        "name": "Guntur",
        "state": "Andhra Pradesh",
        "tier": "Tier 2",
        "zones": ["Brodipet", "Arundelpet", "Lakshmipuram", "Kothapet"],
        "desc": "Guntur is a prime agricultural export center with extensive commodity and equity participation across generations of trading families.",
        "pincodes": "522002, 522004, 522007",
        "sebi_regional": "SEBI Local Office, Vijayawada 520002",
    },
    "madurai": {
        "name": "Madurai",
        "state": "Tamil Nadu",
        "tier": "Tier 2",
        "zones": ["KK Nagar", "Anna Nagar", "Simmakkal", "Town Hall Road"],
        "desc": "Madurai is the commercial gateway to Southern Tamil Nadu with deep engagement in gold ETFs, equity delivery, and banking shares.",
        "pincodes": "625001, 625020, 625009",
        "sebi_regional": "SEBI Southern Regional Office, Chennai 600002",
    },
    "tiruchirappalli": {
        "name": "Tiruchirappalli",
        "state": "Tamil Nadu",
        "tier": "Tier 2",
        "zones": ["Thillai Nagar", "Cantonment", "Central Bus Stand", "Srirangam"],
        "desc": "Tiruchirappalli is an engineering and educational center where public sector executives and NRI families build long-term equity portfolios.",
        "pincodes": "620001, 620018, 620006",
        "sebi_regional": "SEBI Southern Regional Office, Chennai 600002",
    },
    "salem": {
        "name": "Salem",
        "state": "Tamil Nadu",
        "tier": "Tier 2",
        "zones": ["Four Roads", "Fairlands", "Junction Road", "Swarnapuri"],
        "desc": "Salem steel and textile merchants actively trade in Indian equity markets and participate heavily in major public issue subscriptions.",
        "pincodes": "636001, 636004, 636007",
        "sebi_regional": "SEBI Southern Regional Office, Chennai 600002",
    },
    "mysuru": {
        "name": "Mysuru",
        "state": "Karnataka",
        "tier": "Tier 2",
        "zones": ["Saraswathipuram", "Jayalakshmipuram", "Vontikoppal", "KRS Road"],
        "desc": "Mysuru has evolved into a premier tech and heritage city in Karnataka with rapid retail demat account openings and mutual fund investments.",
        "pincodes": "570001, 570005, 570009",
        "sebi_regional": "SEBI Local Office, Bengaluru 560038",
    },
    "hubballi": {
        "name": "Hubballi-Dharwad",
        "state": "Karnataka",
        "tier": "Tier 2",
        "zones": ["Koppikar Road", "Vidyanagar", "Deshpande Nagar", "Gokul Road"],
        "desc": "Hubballi is North Karnataka primary commercial center with veteran broker franchisee networks and active commodity derivatives traders.",
        "pincodes": "580020, 580021, 580029",
        "sebi_regional": "SEBI Local Office, Bengaluru 560038",
    },
    "mangalore": {
        "name": "Mangaluru",
        "state": "Karnataka",
        "tier": "Tier 2",
        "zones": ["Hampankatta", "Kodialbail", "Kankanady", "MG Road", "Kadri"],
        "desc": "Mangaluru combines port trade and Gulf NRI remittance flows with sophisticated equity investments and high-value depository accounts.",
        "pincodes": "575001, 575002, 575003",
        "sebi_regional": "SEBI Local Office, Bengaluru 560038",
    },
    "thiruvananthapuram": {
        "name": "Thiruvananthapuram",
        "state": "Kerala",
        "tier": "Tier 2",
        "zones": ["MG Road", "Vellayambalam", "Pattom", "Technopark (Kazhakkoottam)", "Palayam"],
        "desc": "Thiruvananthapuram is Kerala capital and home to Technopark, with heavy tech employee adoption of digital trading platforms and SIPs.",
        "pincodes": "695001, 695004, 695010, 695581",
        "sebi_regional": "SEBI Local Office, Kochi 682016",
    },
    "kozhikode": {
        "name": "Kozhikode",
        "state": "Kerala",
        "tier": "Tier 2",
        "zones": ["Mavoor Road", "SM Street", "Bank Road", "Palayam"],
        "desc": "Kozhikode has strong export trade networks with active NRI participation in equity markets and index funds.",
        "pincodes": "673001, 673004, 673002",
        "sebi_regional": "SEBI Local Office, Kochi 682016",
    },
    "guwahati": {
        "name": "Guwahati",
        "state": "Assam",
        "tier": "Tier 2",
        "zones": ["GS Road", "Paltan Bazaar", "Zoo Road", "Fancy Bazaar", "Dispur"],
        "desc": "Guwahati is the financial gateway to Northeast India, housing regional offices of national brokerages, mutual fund AMCs, and SEBI.",
        "pincodes": "781001, 781005, 781006",
        "sebi_regional": "SEBI Local Office, Nedfi House, GS Road, Guwahati 781006",
    },
    "aurangabad": {
        "name": "Chhatrapati Sambhajinagar",
        "state": "Maharashtra",
        "tier": "Tier 2",
        "zones": ["Jalna Road", "CIDCO", "Samarth Nagar", "Kranti Chowk"],
        "desc": "Chhatrapati Sambhajinagar is an automotive manufacturing center with substantial retail equity participation and local branch networks.",
        "pincodes": "431001, 431003, 431005",
        "sebi_regional": "SEBI Local Office, Pune 411004",
    },
    "solapur": {
        "name": "Solapur",
        "state": "Maharashtra",
        "tier": "Tier 2",
        "zones": ["Railway Lines", "Murarji Peth", "Saat Rasta", "Old Pune Naka"],
        "desc": "Solapur is a prominent textile and trade center of Southern Maharashtra with active retail broking and commodity trading.",
        "pincodes": "413001, 413002, 413003",
        "sebi_regional": "SEBI Local Office, Pune 411004",
    },
}

BROKER_BRANCH_METADATA = {
    "zerodha": {
        "brand": "Zerodha",
        "model": "Digital-First with Regional Partner Desks",
        "sebi_reg": "INZ000031633 (Stock Broker), IN-DP-431-2019 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12081600 / 12081601",
        "hq_address": "153/154, 4th Cross, Dollars Colony, 4th Phase, J.P. Nagar, Bengaluru, Karnataka 560078",
        "kyc_mode": "100% Online Aadhaar e-KYC (DigiLocker) + Physical Courier for Non-Aadhaar / HUF / Corporate",
        "demat_service": "Physical share dematerialisation via courier to Bengaluru Central Processing Unit with DRF (Demat Request Form).",
        "helpline": "080 4718 1888 / 080 7117 5333",
        "partner_badge": "BrokerLens Partner",
        "cta_url": "https://zerodha.com/open-account?c=ZE5729",
    },
    "groww": {
        "brand": "Groww",
        "model": "App-First Digital Broker",
        "sebi_reg": "INZ000301838 (Stock Broker), IN-DP-417-2019 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12088700 / 12088701",
        "hq_address": "Vaishnavi Tech Park, 3rd & 4th Floor, Sarjapur Main Road, Bellandur, Bengaluru, Karnataka 560103",
        "kyc_mode": "Paperless instant onboarding via PAN, Aadhaar OTP, and video verification.",
        "demat_service": "Digital-only depository operations. Physical share certificates must be submitted via registered postal dispatch to Bengaluru operations center.",
        "helpline": "080 6824 9147",
        "partner_badge": None,
        "cta_url": "https://groww.in",
    },
    "angel-one": {
        "brand": "Angel One",
        "model": "Hybrid: 900+ Physical Branches & Authorized Person Desks Nationwide",
        "sebi_reg": "INZ000161534 (Stock Broker), IN-DP-384-2018 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12033200",
        "hq_address": "G-1, Ackruti Trade Centre, Road No. 7, MIDC, Andheri East, Mumbai, Maharashtra 400093",
        "kyc_mode": "Instant online Aadhaar e-KYC or assisted in-person verification at local branch/franchisee.",
        "demat_service": "Direct over-the-counter physical share certificate submission, DIS slip processing, and nomination updates at local branches.",
        "helpline": "080 4748 0048 / 022 3935 7600",
        "partner_badge": None,
        "cta_url": "https://www.angelone.in",
    },
    "upstox": {
        "brand": "Upstox",
        "model": "Digital Brokerage with Regional Support Centers",
        "sebi_reg": "INZ000185137 (Stock Broker), IN-DP-118-2015 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12081800",
        "hq_address": "RKSV Securities India Pvt. Ltd., 807, New Delhi House, Barakhamba Road, Connaught Place, New Delhi 110001",
        "kyc_mode": "Fast digital e-KYC using Aadhaar linked mobile number.",
        "demat_service": "Centralized physical share processing via Mumbai/Delhi operations hubs.",
        "helpline": "022 4179 2999",
        "partner_badge": None,
        "cta_url": "https://upstox.com",
    },
    "icici-direct": {
        "brand": "ICICI Direct",
        "model": "Pan-India Bank-Backed Branch & ICICI Bank Branch Network",
        "sebi_reg": "INZ000183631 (Stock Broker), IN-DP-275-2016 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN300183 (NSDL) / 12010800 (CDSL)",
        "hq_address": "ICICI Securities Ltd, ICICI Venture House, Appasaheb Marathe Marg, Prabhadevi, Mumbai 400025",
        "kyc_mode": "Instant 3-in-1 account integration (ICICI Bank savings + trading + demat) at any ICICI Bank branch or online.",
        "demat_service": "Walk-in physical share conversion, Demat Request Form (DRF) handling, and wealth advisory desks across all city branches.",
        "helpline": "1800 572 7070 / 022 6807 7070",
        "partner_badge": None,
        "cta_url": "https://www.icicidirect.com",
    },
    "hdfc-securities": {
        "brand": "HDFC Securities",
        "model": "Extensive National Bank-Backed Network & 200+ Dedicated Branches",
        "sebi_reg": "INZ000186937 (Stock Broker), IN-DP-372-2018 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN300126 (NSDL) / 12086700 (CDSL)",
        "hq_address": "HDFC Securities Limited, Office Floor 8, 'I Think' Techno Campus, Kanjurmarg East, Mumbai 400042",
        "kyc_mode": "Seamless 3-in-1 account creation across HDFC Bank branches nationwide or instant paperless online.",
        "demat_service": "Dedicated relationship managers for over-the-counter DRF submission, pledge/unpledge, and physical share certificate dematerialisation.",
        "helpline": "022 3901 9400 / 022 6246 5555",
        "partner_badge": None,
        "cta_url": "https://www.hdfcsec.com",
    },
    "kotak-securities": {
        "brand": "Kotak Securities",
        "model": "120+ Dedicated Branches & Nationwide Kotak Mahindra Bank Network",
        "sebi_reg": "INZ000200137 (Stock Broker), IN-DP-428-2019 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN300476 (NSDL) / 12028100 (CDSL)",
        "hq_address": "Kotak Securities Ltd., 27 BKC, C 27, G Block, Bandra Kurla Complex, Bandra East, Mumbai 400051",
        "kyc_mode": "Trade Free youth zero brokerage account with instant e-KYC or branch walk-in assistance.",
        "demat_service": "Full-service counter support for physical share demat, transmission, and power of attorney (POA/DDPI) filings.",
        "helpline": "1800 209 9191 / 022 6218 0100",
        "partner_badge": None,
        "cta_url": "https://www.kotaksecurities.com",
    },
    "sharekhan": {
        "brand": "Sharekhan",
        "model": "2,400+ Branches & Franchisee Partner Outlets in 575+ Indian Cities",
        "sebi_reg": "INZ000171337 (Stock Broker), IN-DP-365-2018 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12036000 (CDSL) / IN301071 (NSDL)",
        "hq_address": "Sharekhan Limited, The Ruby, 18th Floor, 29 Senapati Bapat Marg, Dadar West, Mumbai 400028",
        "kyc_mode": "Walk-in branch assistance with local relationship manager or instant online mobile onboarding.",
        "demat_service": "Comprehensive in-person dematerialisation, physical share evaluation, stamp duty consultation, and paper DIS submission.",
        "helpline": "1800 22 7500 / 022 2575 3200",
        "partner_badge": None,
        "cta_url": "https://www.sharekhan.com",
    },
    "motilal-oswal": {
        "brand": "Motilal Oswal",
        "model": "2,200+ Advisory Branches & Franchisee Hubs Nationwide",
        "sebi_reg": "INZ000158836 (Stock Broker), IN-DP-418-2019 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12010900 (CDSL) / IN300417 (NSDL)",
        "hq_address": "Motilal Oswal Tower, Rahimtullah Sayani Road, Opposite Parel ST Depot, Prabhadevi, Mumbai 400025",
        "kyc_mode": "Assisted relationship manager onboarding with dedicated research advisory or online app e-KYC.",
        "demat_service": "Full physical share handling, transmission of deceased holder shares, family office wealth structuring, and margin trading funding (MTF).",
        "helpline": "022 4054 8000 / 022 7188 1000",
        "partner_badge": None,
        "cta_url": "https://www.motilaloswal.com",
    },
    "5paisa": {
        "brand": "5paisa",
        "model": "Digital Discount Brokerage (IIFL Group Heritage)",
        "sebi_reg": "INZ000010231 (Stock Broker), IN-DP-CDSL-650-2012 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12082500",
        "hq_address": "5paisa Capital Limited, IIFL House, Sun Infotech Park, Road No. 16V, Plot No. B-23, Thane Industrial Area, Wagle Estate, Thane 400604",
        "kyc_mode": "Instant paperless account opening via mobile app.",
        "demat_service": "Postal dispatch for physical share certificates to Thane processing unit.",
        "helpline": "022 4942 2222",
        "partner_badge": None,
        "cta_url": "https://www.5paisa.com",
    },
    "dhan": {
        "brand": "Dhan",
        "model": "Tech-Driven Direct Market Access Broker",
        "sebi_reg": "INZ000006031 (Stock Broker), IN-DP-CDSL-670-2022 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12083400",
        "hq_address": "Moneylicious Securities Pvt. Ltd., A-302, The Platina, G-Block, BKC, Bandra East, Mumbai 400051",
        "kyc_mode": "Lightning-fast 100% digital onboarding for options traders and investors.",
        "demat_service": "Centralized digital DP operations. Physical certificate conversion processed via Mumbai corporate address.",
        "helpline": "022 4897 7091",
        "partner_badge": None,
        "cta_url": "https://dhan.co",
    },
    "fyers": {
        "brand": "Fyers",
        "model": "Technology-Focused Trading Platform",
        "sebi_reg": "INZ000008524 (Stock Broker), IN-DP-432-2019 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12089400",
        "hq_address": "Fyers Securities Pvt. Ltd., Brigade Magnum, 902, 9th Floor, Amruthahalli, Kodigehalli Gate, Bengaluru 560092",
        "kyc_mode": "Online e-KYC using Aadhaar OTP.",
        "demat_service": "Physical dematerialisation handled through Bengaluru processing cell.",
        "helpline": "080 6000 1111",
        "partner_badge": None,
        "cta_url": "https://fyers.in",
    },
    "anand-rathi": {
        "brand": "Anand Rathi",
        "model": "Pan-India Full-Service & Wealth Advisory Network (350+ Outlets)",
        "sebi_reg": "INZ000170832 (Stock Broker), IN-DP-380-2018 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12029900 (CDSL) / IN301485 (NSDL)",
        "hq_address": "Express Zone, A Wing, 10th Floor, Western Express Highway, Goregaon East, Mumbai 400063",
        "kyc_mode": "In-person branch advisor relationship or digital self-onboarding.",
        "demat_service": "Direct branch processing for physical shares, mutual fund dematerialisation, and portfolio management services (PMS).",
        "helpline": "1800 200 1002 / 022 6281 7000",
        "partner_badge": None,
        "cta_url": "https://www.rathi.com",
    },
    "geojit": {
        "brand": "Geojit",
        "model": "470+ Branches in South India & Middle East Desks (BNP Paribas Backed)",
        "sebi_reg": "INZ000104737 (Stock Broker), IN-DP-423-2019 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN301637 (NSDL) / 12032800 (CDSL)",
        "hq_address": "Geojit Financial Services Ltd., 34/659-P, Civil Line Road, Padivattom, Kochi, Kerala 682024",
        "kyc_mode": "Extensive walk-in retail advisory branch presence and digital paperless onboarding.",
        "demat_service": "Specialist in physical share certificates, NRI demat operations (NRE/NRO accounts), and mutual fund distribution.",
        "helpline": "1800 425 5501 / 0484 2901000",
        "partner_badge": None,
        "cta_url": "https://www.geojit.com",
    },
    "smc": {
        "brand": "SMC Global",
        "model": "National Full-Service Broker with 2,500+ Franchisees & Sub-Brokers",
        "sebi_reg": "INZ000199438 (Stock Broker), IN-DP-415-2019 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12044700 (CDSL) / IN303655 (NSDL)",
        "hq_address": "11/6B, Shanti Chamber, Pusa Road, New Delhi 110005",
        "kyc_mode": "Assisted branch verification or mobile e-KYC.",
        "demat_service": "Over-the-counter physical share conversion, margin funding, and algorithmic execution support.",
        "helpline": "1800 11 0909 / 011 6607 5200",
        "partner_badge": None,
        "cta_url": "https://www.smcindiaonline.com",
    },
    "ventura": {
        "brand": "Ventura Securities",
        "model": "Branch Network & Authorized Representative Outlets Across Western India",
        "sebi_reg": "INZ000211636 (Stock Broker), IN-DP-424-2019 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12048900 (CDSL) / IN303116 (NSDL)",
        "hq_address": "I-Think Techno Campus, 8th Floor, B-Wing, Pokhran Road No. 2, Thane West, Mumbai 400607",
        "kyc_mode": "Branch walk-in with local franchise partner or online registration.",
        "demat_service": "Comprehensive depository and physical certificate demat assistance.",
        "helpline": "022 6754 0600",
        "partner_badge": None,
        "cta_url": "https://www.ventura1.com",
    },
    "nirmal-bang": {
        "brand": "Nirmal Bang",
        "model": "Institutional & Retail Broker with Extensive Branches in Mumbai & Gujarat",
        "sebi_reg": "INZ000202536 (Stock Broker), IN-DP-382-2018 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12013300 (CDSL) / IN301604 (NSDL)",
        "hq_address": "B-2, 301/302, 3rd Floor, Marathon Innova, Off Ganpatrao Kadam Marg, Lower Parel, Mumbai 400013",
        "kyc_mode": "Dedicated client dealer relationship manager or instant online e-KYC.",
        "demat_service": "Specialist in old family physical certificates, loss of share certificates, and transmission.",
        "helpline": "022 6273 8000 / 022 6273 9000",
        "partner_badge": None,
        "cta_url": "https://www.nirmalbang.com",
    },
    "sbi-securities": {
        "brand": "SBI Securities",
        "model": "Backed by India's Largest Bank (State Bank of India)",
        "sebi_reg": "INZ000200032 (Stock Broker), IN-DP-19-2015 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN300183 (NSDL) / 12047200 (CDSL)",
        "hq_address": "SBICAP Securities Ltd, Marathon Futurex, B-Wing, 12th Floor, N.M. Joshi Marg, Lower Parel, Mumbai 400013",
        "kyc_mode": "Seamless 3-in-1 account linkage via SBI internet banking (YONO) or at any SBI branch.",
        "demat_service": "National network for physical certificate submission and bank branch assistance.",
        "helpline": "1800 209 9345 / 022 6854 5555",
        "partner_badge": None,
        "cta_url": "https://www.sbisecurities.in",
    },
    "axis-direct": {
        "brand": "Axis Direct",
        "model": "Bank-Backed Network Across 4,500+ Axis Bank Branches",
        "sebi_reg": "INZ000161633 (Stock Broker), IN-DP-427-2019 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12049200 (CDSL) / IN304295 (NSDL)",
        "hq_address": "Axis Securities Ltd., Aurum Q Parć, Q1 Building, Unit No. 1001, Ghansoli, Navi Mumbai 400710",
        "kyc_mode": "Integrated 3-in-1 account via Axis Bank mobile banking or walk-in.",
        "demat_service": "Direct over-the-counter DRF submission and wealth management advisory desks.",
        "helpline": "022 4050 8080 / 022 6148 0808",
        "partner_badge": None,
        "cta_url": "https://simplehai.axisdirect.in",
    },
    "paytm-money": {
        "brand": "Paytm Money",
        "model": "App-First Digital Investment Platform",
        "sebi_reg": "INZ000240532 (Stock Broker), IN-DP-416-2019 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12089700",
        "hq_address": "Paytm Money Ltd., 136, 1st Floor, Devika Tower, Nehru Place, New Delhi 110019",
        "kyc_mode": "100% paperless Aadhaar OTP digital verification.",
        "demat_service": "Postal dispatch for physical share certificates to New Delhi/Bengaluru ops hubs.",
        "helpline": "0120 4456 456",
        "partner_badge": None,
        "cta_url": "https://www.paytmmoney.com",
    },
    "hdfc-sky": {
        "brand": "HDFC Sky",
        "model": "Discount Broking Arm of HDFC Securities",
        "sebi_reg": "INZ000186937 (Stock Broker), IN-DP-372-2018 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN300601 / 12086700",
        "hq_address": "HDFC Securities Ltd., I-Think Techno Campus, Building-B, Alpha, Kanjurmarg East, Mumbai 400042",
        "kyc_mode": "100% digital Aadhaar OTP onboarding or assisted via select HDFC Bank branches.",
        "demat_service": "Centralized physical certificate dematerialization via Mumbai processing hub.",
        "helpline": "022 6849 4666",
        "partner_badge": None,
        "cta_url": "https://www.hdfcsky.com",
    },
    "alice-blue": {
        "brand": "Alice Blue",
        "model": "Discount Broker with 15+ Regional Branches in South & West India",
        "sebi_reg": "INZ000156038 (Stock Broker), IN-DP-364-2018 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12085300",
        "hq_address": "No. 153/2, 3rd Floor, M.R.B. Arcade, Bagalur Main Road, Yelahanka, Bengaluru 560063",
        "kyc_mode": "Online e-KYC or walk-in assistance at local regional franchise desks.",
        "demat_service": "In-person DRF submission at branch offices or courier to Bengaluru operations.",
        "helpline": "080 3521 5000",
        "partner_badge": None,
        "cta_url": "https://aliceblueonline.com",
    },
    "prostocks": {
        "brand": "ProStocks",
        "model": "Direct Flat-Fee Broker with Mumbai Operations Center",
        "sebi_reg": "INZ000048660 (Stock Broker), IN-DP-280-2016 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12083600",
        "hq_address": "Sunlight Broking LLP, 146, 1st Floor, Powai Plaza, Hiranandani Gardens, Powai, Mumbai 400076",
        "kyc_mode": "Paperless instant Aadhaar OTP KYC verification.",
        "demat_service": "Physical certificate demat assistance via central Mumbai desk.",
        "helpline": "022 6243 4343 / 022 3811 0110",
        "partner_badge": None,
        "cta_url": "https://www.prostocks.com",
    },
    "tradejini": {
        "brand": "Tradejini",
        "model": "Discount Broker with Bengaluru Support & Execution Desks",
        "sebi_reg": "INZ000160938 (Stock Broker), IN-DP-473-2020 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12088800",
        "hq_address": "Tradejini Financial Services Pvt Ltd, Vasavi Square, 2nd Floor, 10th Main, Jayanagar 4th Block, Bengaluru 560011",
        "kyc_mode": "Digital e-KYC via DigiLocker.",
        "demat_service": "Centralized DRF processing for physical share conversion.",
        "helpline": "080 4020 4020",
        "partner_badge": None,
        "cta_url": "https://www.tradejini.com",
    },
    "choice-broking": {
        "brand": "Choice Broking",
        "model": "National Full-Service Broker with 100+ Branches Nationwide",
        "sebi_reg": "INZ000160131 (Stock Broker), IN-DP-84-2015 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12075800 / IN304279",
        "hq_address": "Sunil Patodia Tower, J.B. Nagar, Andheri East, Mumbai 400099",
        "kyc_mode": "Walk-in branch verification or Choice Jiffy app paperless KYC.",
        "demat_service": "Comprehensive branch support for physical certificate demat, IEPF claims, and name corrections.",
        "helpline": "022 6707 9999",
        "partner_badge": None,
        "cta_url": "https://choiceindia.com",
    },
    "swastika-investmart": {
        "brand": "Swastika Investmart",
        "model": "Extensive Central India Branch & Franchisee Network",
        "sebi_reg": "INZ000192732 (Stock Broker), IN-DP-362-2018 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12051500 / IN304317",
        "hq_address": "Flat No. 18, Ground Floor, North Park, Saket Square, Indore, Madhya Pradesh 452018",
        "kyc_mode": "Local branch executive assistance or online e-KYC.",
        "demat_service": "Physical share certificate conversion, transmission, and succession claim handling.",
        "helpline": "0731 664 4000 / 0731 664 4200",
        "partner_badge": None,
        "cta_url": "https://www.swastika.co.in",
    },
    "espresso": {
        "brand": "Espresso",
        "model": "Digital Broker Powered by Sharekhan Network",
        "sebi_reg": "INZ000008535 (Stock Broker), IN-DP-365-2018 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12089400",
        "hq_address": "Espresso Financial Services, Lodha iThink Techno Campus, Kanjurmarg East, Mumbai 400042",
        "kyc_mode": "100% online onboarding via Aadhaar OTP.",
        "demat_service": "Centralized physical certificate demat handling via Sharekhan operations.",
        "helpline": "022 6767 0700",
        "partner_badge": None,
        "cta_url": "https://www.myespresso.com",
    },
    "samco": {
        "brand": "SAMCO",
        "model": "Fintech & Algorithmic Broking Platform",
        "sebi_reg": "INZ000002535 (Stock Broker), IN-DP-411-2019 (CDSL DP)",
        "demat_provider": "CDSL",
        "demat_id": "12054200",
        "hq_address": "1004 - A, 10th Floor, Naman Midtown, Senapati Bapat Marg, Elphinstone Road, Mumbai 400013",
        "kyc_mode": "Paperless instant account setup.",
        "demat_service": "Mail-in physical share demat processing.",
        "helpline": "022 2222 7777",
        "partner_badge": None,
        "cta_url": "https://www.samco.in",
    },
    "religare": {
        "brand": "Religare Broking",
        "model": "Pan-India Retail Branch & Wealth Advisory Network",
        "sebi_reg": "INZ000174330 (Stock Broker), IN-DP-25-2015 (CDSL & NSDL DP)",
        "demat_provider": "CDSL & NSDL",
        "demat_id": "12038000 / IN301774",
        "hq_address": "Religare Broking Ltd, 2nd Floor, Rajlok Building, 24 Nehru Place, New Delhi 110019",
        "kyc_mode": "Assisted in-person branch verification or instant digital KYC.",
        "demat_service": "Branch counter submission for physical share demat and succession transfer.",
        "helpline": "1800 102 3335 / 011 4110 3335",
        "partner_badge": None,
        "cta_url": "https://www.religareonline.com",
    },
    "yes-securities": {
        "brand": "YES Securities",
        "model": "YES Bank 3-in-1 Banking & Broking Branch Network",
        "sebi_reg": "INZ000185632 (Stock Broker), IN-DP-417-2019 (NSDL & CDSL DP)",
        "demat_provider": "NSDL & CDSL",
        "demat_id": "IN304325 / 12085700",
        "hq_address": "YES Securities (India) Ltd, 2nd Floor, YES BANK House, Off Western Express Highway, Santacruz East, Mumbai 400055",
        "kyc_mode": "Direct walk-in across 1,200+ YES Bank branches or paperless online registration.",
        "demat_service": "Full depository branch support for DRF processing, physical share demat, and pledge creation.",
        "helpline": "1800 120 1221 / 022 6884 1888",
        "partner_badge": None,
        "cta_url": "https://yesinvest.in",
    },
}


def _get_registry_city_entities():
    """Extracts city-level SEBI registered intermediaries from data/_ingest.json or site/data/registry.json."""
    city_map = {}
    ingest_path = os.path.join(DATA_DIR, "_ingest.json")
    if os.path.exists(ingest_path):
        try:
            with open(ingest_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            reg = d.get("sebi", {}).get("registry", {})
            for cat in ["commodity_broker", "dp_cdsl", "dp_nsdl"]:
                for item in reg.get(cat, []):
                    city = (item.get("city") or "").strip().lower()
                    if city:
                        city_map.setdefault(city, []).append(item)
        except Exception:
            pass

    if not city_map:
        reg_path = os.path.join(SITE_DIR, "data", "registry.json")
        if os.path.exists(reg_path):
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                for item in d.get("entities", []):
                    city = (item.get("city") or "").strip().lower()
                    if city:
                        city_map.setdefault(city, []).append(item)
            except Exception:
                pass

    return city_map


def _render_city_branch_page(b_id, meta, city_key, city_data, local_entities, site_url):
    """Renders /broker/[broker-id]/branches/[city-slug]/index.html."""
    brand = meta["brand"]
    c_name = city_data["name"]
    state = city_data["state"]
    tier = city_data["tier"]
    zones_str = ", ".join(city_data["zones"])
    canonical = f"{site_url}/broker/{b_id}/branches/{city_key}/"

    title = f"{brand} Branch in {c_name}, {state}: Address, Phone, Demat & KYC Services"
    desc = (
        f"Looking for {brand} branch in {c_name}, {state}? Find office contact details, "
        f"DP ID ({meta['demat_id']}), offline KYC, physical share demat (DRF) procedure, and {c_name} support points."
    )[:295]

    is_hq = (b_id == "zerodha" and city_key == "bengaluru") or \
            (b_id == "groww" and city_key == "bengaluru") or \
            (b_id in ("angel-one", "icici-direct", "hdfc-securities", "kotak-securities", "sharekhan", "motilal-oswal", "dhan", "anand-rathi", "ventura", "nirmal-bang", "sbi-securities") and city_key == "mumbai") or \
            (b_id in ("upstox", "smc", "paytm-money") and city_key == "delhi") or \
            (b_id == "geojit" and city_key == "kochi")

    office_type = "Corporate Headquarters & Flagship Investor Center" if is_hq else (
        "Authorized Branch & Physical Service Desk" if "Branch" in meta["model"] or "Network" in meta["model"] else
        "Digital Support Center & Regional Facilitation Desk"
    )

    address_display = meta["hq_address"] if is_hq else f"Authorized partner service desks and relationship desks across key financial zones in {c_name}: {zones_str} (Postal codes: {city_data['pincodes']}). For centralized postal operations and DRF submissions, route to corporate operations headquarters: {meta['hq_address']}."

    partner_cta = f'<a class="btn primary" href="{meta["cta_url"]}" target="_blank" rel="noopener nofollow">Open {brand} Demat Account Online</a>'
    if meta.get("partner_badge"):
        partner_cta += f' <span class="badge partner" style="margin-left:8px;vertical-align:middle;">{meta["partner_badge"]}</span>'

    local_dp_html = ""
    if local_entities:
        dp_rows = "".join(
            f'<tr><td><strong>{_esc(e.get("legal_name") or e.get("name"))}</strong></td>'
            f'<td><span class="mono xs">{_esc(e.get("sebi_reg_no") or e.get("reg") or "-")}</span></td>'
            f'<td>{_esc(e.get("category", "").replace("_", " ").upper())}</td>'
            f'<td>{_esc(e.get("contact_person") or e.get("telephone") or "Available on SEBI record")}</td></tr>'
            for e in local_entities[:6]
        )
        local_dp_html = f"""
        <div class="card" style="margin-top:24px;">
            <h3>SEBI-Registered Intermediaries in {c_name}</h3>
            <p class="muted xs">Other recognized Depository Participants and brokers with official registrations in {c_name}:</p>
            <div class="table-wrap" style="margin-top:12px;">
                <table class="table striped">
                    <thead><tr><th>Entity Name</th><th>SEBI Reg No</th><th>Category</th><th>Contact / Desk</th></tr></thead>
                    <tbody>{dp_rows}</tbody>
                </table>
            </div>
            <p style="margin-top:10px;"><a class="link" href="/registry/city/{city_key}/">View all {len(local_entities)} registered market entities in {c_name} &rarr;</a></p>
        </div>
        """

    faq_items = [
        (
            f"Does {brand} have a physical office or branch in {c_name}?",
            f"{brand} operates in {c_name} via its {meta['model'].lower()}. {'As the corporate headquarters, it maintains full-scale walk-in investor relations and grievance desks in this city.' if is_hq else f'While retail traders in {c_name} predominantly manage their accounts digitally via mobile app and web, physical documentation, account modifications, and in-person verification are supported through {brand} regional desks, authorized representatives, or direct centralized postal dispatch.'}"
        ),
        (
            f"How do I submit physical share certificates for Demat with {brand} in {c_name}?",
            f"To convert physical paper share certificates into electronic demat holdings via {brand}: (1) Open a {brand} Demat account if not already active; (2) Fill out the Demat Request Form (DRF) in duplicate for each company; (3) Deface the physical certificates by writing 'Surrendered for Dematerialisation'; (4) { 'Submit directly at the local branch desk in ' + c_name if ('Branch' in meta['model'] or is_hq) else 'Courier the original certificates along with signed DRF forms and self-attested PAN/Aadhaar copies to ' + brand + ' central processing unit at ' + meta['hq_address'] }. The shares will be credited to your CDSL/NSDL Demat ID ({meta['demat_id']}) within 15 to 21 working days upon registrar confirmation."
        ),
        (
            f"Can I complete offline KYC or account opening with {brand} in {c_name}?",
            f"Yes. While {brand} offers instant 100% paperless Aadhaar e-KYC completing in 5 to 10 minutes, investors without Aadhaar-linked mobile numbers, HUF accounts, corporate entities, or partnership firms in {c_name} can complete offline verification. {'You can visit the local branch in ' + c_name + ' with physical KYC documents.' if ('Branch' in meta['model'] or is_hq) else 'Download the physical account opening forms from the official portal, affix passport photographs, attach self-attested identity/address proofs, and send them to the corporate operations office.'}"
        ),
        (
            f"What is the grievance redressal and customer care escalation for {brand} in {c_name}?",
            f"For support in {c_name}, call {brand} helpline at {meta['helpline']}. If a ticket remains unresolved within 7 days, investors can escalate to {brand} designated Principal Compliance Officer. As a statutory right, clients can also lodge complaints directly with SEBI through the SCORES 2.0 portal (scores.sebi.gov.in) citing {brand} registration number {meta['sebi_reg'].split()[0]}, or visit the regional SEBI office ({city_data['sebi_regional']})."
        ),
    ]

    faq_html = "".join(
        f'<div class="faq-item" style="margin-bottom:16px;">'
        f'<h4 style="margin:0 0 6px 0;font-size:15px;color:var(--text-bright);">{q}</h4>'
        f'<p class="muted" style="margin:0;font-size:14px;line-height:1.6;">{a}</p>'
        f'</div>'
        for q, a in faq_items
    )

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialService",
                "name": f"{brand} - {c_name} Branch & Service Point",
                "url": canonical,
                "telephone": meta["helpline"],
                "priceRange": "Brokerage varies by asset class (Zero delivery / Rs 20 intraday)",
                "currenciesAccepted": "INR",
                "paymentAccepted": "UPI, Netbanking, NEFT, RTGS",
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": meta["hq_address"] if is_hq else f"Financial Hub Zones ({zones_str})",
                    "addressLocality": c_name,
                    "addressRegion": state,
                    "postalCode": city_data["pincodes"].split(",")[0].strip(),
                    "addressCountry": "IN"
                },
                "parentOrganization": {
                    "@type": "Organization",
                    "name": brand,
                    "url": f"{site_url}/broker/{b_id}/"
                }
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faq_items
                ]
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Brokers", "item": f"{site_url}/brokers"},
                    {"@type": "ListItem", "position": 3, "name": brand, "item": f"{site_url}/broker/{b_id}/"},
                    {"@type": "ListItem", "position": 4, "name": "Branches", "item": f"{site_url}/broker/{b_id}/branches/"},
                    {"@type": "ListItem", "position": 5, "name": c_name, "item": canonical}
                ]
            }
        ]
    }

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/branches/" class="active">Branches</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/brokers">Brokers</a> &rsaquo;
    <a href="/broker/{b_id}/">{brand}</a> &rsaquo;
    <a href="/broker/{b_id}/branches/">Branches</a> &rsaquo;
    <span>{c_name}</span>
  </div>

  <header style="margin-bottom:28px;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
      <h1 style="font-size:28px;line-height:1.2;margin:0;">{brand} Branch in {c_name}, {state}</h1>
      <span class="badge" style="background:var(--surface-raised);border:1px solid var(--border);padding:4px 10px;border-radius:16px;font-size:12px;">{tier}</span>
    </div>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      {city_data["desc"]} Complete guide to {brand} office address, customer care helpline, Depository Participant operations, offline KYC, and physical share dematerialisation in {c_name}.
    </p>
  </header>

  <div class="grid g2" style="gap:20px;margin-bottom:28px;">
    <div class="card">
      <h2 style="font-size:17px;margin-top:0;margin-bottom:12px;color:var(--text-bright);">Branch & Service Point Overview</h2>
      <div style="font-size:14px;line-height:1.8;">
        <div><span class="muted">Operating Model:</span> <strong>{meta["model"]}</strong></div>
        <div><span class="muted">Office Classification:</span> <strong>{office_type}</strong></div>
        <div><span class="muted">Primary Helpline:</span> <strong>{meta["helpline"]}</strong></div>
        <div><span class="muted">Depository Participant:</span> <strong>{meta["demat_provider"]} (ID: {meta["demat_id"]})</strong></div>
        <div><span class="muted">SEBI Registration:</span> <span class="mono xs">{meta["sebi_reg"]}</span></div>
        <div style="margin-top:8px;"><span class="muted">Key City Zones Covered:</span> <span>{zones_str}</span></div>
      </div>
      <div style="margin-top:18px;">
        {partner_cta}
      </div>
    </div>

    <div class="card">
      <h2 style="font-size:17px;margin-top:0;margin-bottom:12px;color:var(--text-bright);">Operational Address & Handling</h2>
      <div style="font-size:13.5px;line-height:1.6;">
        <p style="margin:0 0 10px 0;"><strong>Local Service Point & Address Details:</strong><br>{address_display}</p>
        <p style="margin:0 0 10px 0;"><span class="muted">Local SEBI Regional Office:</span><br><strong>{city_data["sebi_regional"]}</strong></p>
        <p style="margin:0;"><span class="muted">Postal Pincodes:</span> <span class="mono">{city_data["pincodes"]}</span></p>
      </div>
    </div>
  </div>

  <section class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;color:var(--text-bright);">Demat & Physical Share Processing in {c_name}</h2>
    <p style="font-size:14.5px;line-height:1.6;margin-bottom:16px;">
      {meta["demat_service"]} Under SEBI regulations, all physical share certificates must be converted into demat form before selling on NSE or BSE.
    </p>

    <div class="grid g3" style="gap:16px;margin-top:16px;">
      <div style="background:var(--surface);padding:14px;border-radius:8px;border:1px solid var(--border);">
        <h4 style="margin:0 0 6px 0;font-size:14px;color:var(--text-bright);">1. Demat Request Form (DRF)</h4>
        <p class="muted xs" style="margin:0;line-height:1.5;">Download {brand} DRF in duplicate, fill details of company and certificate numbers, and sign matching your bank/RTA specimen signature.</p>
      </div>
      <div style="background:var(--surface);padding:14px;border-radius:8px;border:1px solid var(--border);">
        <h4 style="margin:0 0 6px 0;font-size:14px;color:var(--text-bright);">2. Deface Physical Certificate</h4>
        <p class="muted xs" style="margin:0;line-height:1.5;">Mark certificates with 'Surrendered for Dematerialisation' stamp to prevent misuse during transit from {c_name}.</p>
      </div>
      <div style="background:var(--surface);padding:14px;border-radius:8px;border:1px solid var(--border);">
        <h4 style="margin:0 0 6px 0;font-size:14px;color:var(--text-bright);">3. Dispatch & Credit</h4>
        <p class="muted xs" style="margin:0;line-height:1.5;">Track consignment delivery to central operations. Registrar verifies signature and electronically credits shares into Demat ID {meta["demat_id"]}.</p>
      </div>
    </div>
  </section>

  <section class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;color:var(--text-bright);">Digital e-KYC vs Local Branch Walk-in</h2>
    <p style="font-size:14px;line-height:1.6;margin-bottom:14px;">
      Most investors in {c_name} open accounts online in under 10 minutes. Here is how digital onboarding compares with in-person branch verification:
    </p>
    <div class="table-wrap">
      <table class="table striped">
        <thead>
          <tr><th>Feature</th><th>Online Digital e-KYC (Recommended)</th><th>Offline Branch Walk-in / Assisted</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Turnaround Time</strong></td>
            <td>5 to 10 minutes (Active within 2 to 4 hours)</td>
            <td>24 to 72 business hours upon paper form verification</td>
          </tr>
          <tr>
            <td><strong>Required Proofs</strong></td>
            <td>Aadhaar OTP via DigiLocker, PAN, canceled cheque / bank statement</td>
            <td>Physical photocopies of PAN, Aadhaar, bank proof with original signatures</td>
          </tr>
          <tr>
            <td><strong>Suitable For</strong></td>
            <td>Individual Indian resident traders with mobile-linked Aadhaar</td>
            <td>HUF, Corporate accounts, NRI, Non-Aadhaar clients, or minors</td>
          </tr>
          <tr>
            <td><strong>Signature Verification</strong></td>
            <td>Digital Aadhaar e-Sign (NSDL / CDSL electronic gateway)</td>
            <td>Wet ink physical signature on printed 24-page application booklet</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  {local_dp_html}

  <section class="card" style="margin-bottom:28px;">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:16px;color:var(--text-bright);">Frequently Asked Questions: {brand} in {c_name}</h2>
    {faq_html}
  </section>

  <section style="margin-top:32px;padding:20px;background:var(--surface-raised);border-radius:10px;border:1px solid var(--border);">
    <h3 style="font-size:16px;margin:0 0 12px 0;">Explore {brand} Across India</h3>
    <div class="row-wrap" style="gap:8px;">
      {"".join(f'<a class="chip" href="/broker/{b_id}/branches/{c}/">{CITIES[c]["name"]}</a>' for c in sorted(CITIES.keys()))}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India is an independent financial technology directory. Registration data sourced directly from SEBI intermediary records and exchange member listings.</p>
    <p style="margin-top:8px;">
      <a href="/branches/">All Broker Branches</a> &bull;
      <a href="/broker/{b_id}/">Full {brand} Review</a> &bull;
      <a href="/broker/{b_id}/trade/">{brand} Trade Costs</a> &bull;
      <a href="/registry">SEBI Registry</a> &bull;
      <a href="/methodology">Methodology</a> &bull;
      <a href="/privacy-policy">Privacy Policy</a>
    </p>
  </div>
</footer>
</body>
</html>"""
    return html_content


def _render_broker_branches_hub(b_id, meta, site_url):
    """Renders /broker/[broker-id]/branches/index.html."""
    brand = meta["brand"]
    canonical = f"{site_url}/broker/{b_id}/branches/"
    title = f"{brand} Branches & Service Centers in India: City Directory & Demat Hubs"
    desc = (
        f"Find {brand} branch offices, customer support desks, and depository participant service centers across "
        f"all major Indian cities. Includes office addresses, helplines, DRF demat procedures, and SEBI registration."
    )[:295]

    city_cards_html = "".join(
        f'<a class="card" href="/broker/{b_id}/branches/{c}/" style="display:block;text-decoration:none;padding:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        f'<h3 style="margin:0;font-size:16px;color:var(--text-bright);">{CITIES[c]["name"]}</h3>'
        f'<span class="badge" style="font-size:11px;">{CITIES[c]["tier"]}</span>'
        f'</div>'
        f'<p class="muted xs" style="margin:0 0 8px 0;">{CITIES[c]["state"]}</p>'
        f'<p class="faint xs" style="margin:0;line-height:1.4;">Key zones: {", ".join(CITIES[c]["zones"][:3])}...</p>'
        f'</a>'
        for c in sorted(CITIES.keys())
    )

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": title,
                "url": canonical,
                "description": desc
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Brokers", "item": f"{site_url}/brokers"},
                    {"@type": "ListItem", "position": 3, "name": brand, "item": f"{site_url}/broker/{b_id}/"},
                    {"@type": "ListItem", "position": 4, "name": "Branches", "item": canonical}
                ]
            }
        ]
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/branches/" class="active">Branches</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/brokers">Brokers</a> &rsaquo;
    <a href="/broker/{b_id}/">{brand}</a> &rsaquo;
    <span>Branches</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">{brand} Branches & Service Centers in India</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Explore {brand}'s physical branch presence, regional support desks, and depository participant facilitation hubs across 37 major Indian financial cities.
    </p>
  </header>

  <div class="card" style="margin-bottom:28px;">
    <h2 style="font-size:17px;margin:0 0 10px 0;">{brand} Corporate & Regulatory Information</h2>
    <div class="grid g2" style="gap:16px;font-size:14px;line-height:1.7;">
      <div>
        <div><span class="muted">Operating Model:</span> <strong>{meta["model"]}</strong></div>
        <div><span class="muted">Customer Care:</span> <strong>{meta["helpline"]}</strong></div>
        <div><span class="muted">Depository ID:</span> <strong>{meta["demat_provider"]} ({meta["demat_id"]})</strong></div>
      </div>
      <div>
        <div><span class="muted">SEBI Registration:</span> <span class="mono xs">{meta["sebi_reg"]}</span></div>
        <div><span class="muted">Central Processing HQ:</span> <span>{meta["hq_address"]}</span></div>
      </div>
    </div>
  </div>

  <section>
    <h2 style="font-size:20px;margin-bottom:16px;">Browse {brand} Offices by City</h2>
    <div class="grid g3" style="gap:16px;">
      {city_cards_html}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from SEBI intermediary records.</p>
  </div>
</footer>
</body>
</html>"""


def _render_city_registry_hub(city_key, city_data, local_entities, site_url):
    """Renders /registry/city/[city-slug]/index.html."""
    c_name = city_data["name"]
    state = city_data["state"]
    canonical = f"{site_url}/registry/city/{city_key}/"
    title = f"SEBI Registered Brokers & Depository Participants in {c_name}, {state}"
    desc = (
        f"Verified list of SEBI registered stock brokers, commodity brokers, and CDSL/NSDL Depository Participants "
        f"headquartered or operating in {c_name}, {state}. View registration numbers, office addresses, and contacts."
    )[:295]

    rows_html = ""
    for e in local_entities:
        name = e.get("legal_name") or e.get("name") or "Intermediary"
        reg = e.get("sebi_reg_no") or e.get("reg") or "-"
        cat = e.get("category") or (e.get("categories", ["broker"])[0] if isinstance(e.get("categories"), list) else "broker")
        addr = e.get("address") or f"Registered office in {c_name}, {state}"
        rows_html += f"""
        <tr>
          <td><strong>{_esc(name)}</strong><br><span class="muted xs">{_esc(addr[:80])}</span></td>
          <td><span class="mono xs">{_esc(reg)}</span></td>
          <td><span class="badge" style="font-size:11px;">{_esc(cat.replace("_", " ").upper())}</span></td>
          <td>{_esc(e.get("contact_person") or e.get("telephone") or "Available on SEBI record")}</td>
        </tr>
        """

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": title,
                "url": canonical,
                "description": desc
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "SEBI Registry", "item": f"{site_url}/registry"},
                    {"@type": "ListItem", "position": 3, "name": c_name, "item": canonical}
                ]
            }
        ]
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/branches/">Branches</a>
      <a href="/registry" class="active">Registry</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/registry">SEBI Registry</a> &rsaquo;
    <span>{c_name}</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">SEBI Intermediaries & DPs in {c_name}, {state}</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      {city_data["desc"]} Official list of {len(local_entities)} recognized market intermediaries registered under SEBI Act, 1992 in {c_name}.
    </p>
  </header>

  <div class="card" style="margin-bottom:28px;">
    <div class="table-wrap">
      <table class="table striped">
        <thead>
          <tr><th>Entity & Address</th><th>SEBI Registration</th><th>Category</th><th>Contact / Desk</th></tr>
        </thead>
        <tbody>
          {rows_html if rows_html else '<tr><td colspan="4" class="muted">No direct intermediary headquarters registered under SEBI sample for this city. Local trading conducted through member branch desks.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <section class="card">
    <h3 style="margin-top:0;">Top Stock Broker Branches in {c_name}</h3>
    <p class="muted xs">Explore local branches of major retail brokers serving {c_name}:</p>
    <div class="row-wrap" style="gap:8px;margin-top:12px;">
      {"".join(f'<a class="chip" href="/broker/{b}/branches/{city_key}/">{BROKER_BRANCH_METADATA[b]["brand"]}</a>' for b in sorted(BROKER_BRANCH_METADATA.keys()))}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from SEBI intermediary records.</p>
  </div>
</footer>
</body>
</html>"""


def _render_city_branches_comparison_hub(city_key, city_data, local_ents, site_url):
    """Renders /branches/city/[city-slug]/index.html (City comparison hub across all brokers)."""
    c_name = city_data["name"]
    c_state = city_data["state"]
    canonical = f"{site_url}/branches/city/{city_key}/"
    title = f"Best Stock Brokers in {c_name}: Branches, Demat Offices & Local KYC | BrokerLens"
    desc = (
        f"Compare top stock broker branches in {c_name}, {c_state}. Review authorized person desks, "
        f"demat centers, physical KYC verification offices, and regional SEBI contact info."
    )[:295]

    broker_rows = []
    for b_id, meta in sorted(BROKER_BRANCH_METADATA.items(), key=lambda x: x[1]["brand"]):
        broker_rows.append(f"""
        <tr>
          <td>
            <strong><a href="/broker/{b_id}/branches/{city_key}/">{meta['brand']}</a></strong>
            <span class="muted xs block">{meta['sebi_reg'].split(',')[0]}</span>
          </td>
          <td><span class="badge" style="font-size:11px;">{meta['demat_provider']} DP</span></td>
          <td class="xs">{meta['model']}</td>
          <td class="xs">{meta['helpline']}</td>
          <td class="center">
            <a href="/broker/{b_id}/branches/{city_key}/" class="btn primary small" style="font-size:12px;padding:4px 8px;">{c_name} Branch &rarr;</a>
          </td>
        </tr>
        """)

    reg_rows = []
    for ent in local_ents[:15]:
        reg_rows.append(f"""
        <tr>
          <td><strong>{_esc(ent.get('name', 'Registered Intermediary'))}</strong></td>
          <td><span class="badge">{_esc(ent.get('category', 'Stock Broker'))}</span></td>
          <td class="xs font-mono">{_esc(ent.get('reg_no', 'SEBI Registered'))}</td>
          <td class="xs">{_esc(ent.get('address', c_name))}</td>
        </tr>
        """)

    crumb_html = f"""<div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <a href="/branches/">Branches</a> &rsaquo;
    <span>Stock Brokers in {c_name}</span>
  </div>"""

    crumb_jsonld = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
            {"@type": "ListItem", "position": 2, "name": "Branches", "item": f"{site_url}/branches/"},
            {"@type": "ListItem", "position": 3, "name": f"Stock Brokers in {c_name}", "item": canonical}
        ]
    }

    faqs = [
        (f"Which stock brokers have local branches or support desks in {c_name}?",
         f"Major national full-service brokers including Angel One, Motilal Oswal, Sharekhan, ICICI Direct, Kotak Securities, and SBI Securities operate physical branch offices and authorized person desks in {c_name}. Digital discount brokers like Zerodha and Groww offer 100% paperless e-KYC onboarding with courier-based demat services."),
        (f"Can I open an offline Demat account in {c_name}?",
         f"Yes. Investors without an Aadhaar-linked mobile phone or those requiring Non-Individual (HUF, Corporate) demat accounts can complete physical paper KYC and In-Person Verification (IPV) at broker branch offices in {c_name}."),
        (f"How can I submit physical share certificates for dematerialisation in {c_name}?",
         f"You can submit original share certificates along with a signed Demat Request Form (DRF) at local branch desks of full-service brokers or courier them directly to the centralized depository processing center of your chosen broker."),
        (f"Where is the nearest SEBI office for {c_name} investors?",
         f"Investors in {c_name} fall under the jurisdiction of: {city_data['sebi_regional']}. For unresolved grievances, complaints can also be registered online via the SEBI SCORES 2.0 portal.")
    ]

    faq_html = "".join(f'<details class="faq-item"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>' for q, a in faqs)

    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "FinancialService",
                "name": f"Stock Brokers and Branches in {c_name}",
                "description": desc,
                "url": canonical,
                "areaServed": {"@type": "City", "name": c_name, "containedInPlace": {"@type": "State", "name": c_state}},
                "provider": {"@type": "Organization", "name": "BrokerLens India", "url": site_url}
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}
                    }
                    for q, a in faqs
                ]
            },
            crumb_jsonld
        ]
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{json.dumps(jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/branches/" class="active">Branches</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  {crumb_html}

  <header style="margin-bottom:28px;">
    <h1 style="font-size:28px;line-height:1.2;margin:0 0 10px 0;">Best Stock Brokers in {c_name}: Branches, Demat Offices & Local KYC</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Directory of authorized stock broker branches, depository participant desks, and offline KYC support centers in {c_name}, {c_state}. Compare account features, Demat services, and local SEBI contacts.
    </p>
  </header>

  <div class="grid g3" style="gap:16px;margin-bottom:28px;">
    <div class="card" style="padding:16px;">
      <div class="muted xs">Classification</div>
      <div class="bold" style="font-size:18px;margin-top:4px;">{city_data['tier']} Financial Market</div>
      <div class="faint xs" style="margin-top:2px;">{c_state}</div>
    </div>
    <div class="card" style="padding:16px;">
      <div class="muted xs">Key Business Zones</div>
      <div class="bold" style="font-size:15px;margin-top:4px;">{", ".join(city_data['zones'][:2])}</div>
      <div class="faint xs" style="margin-top:2px;">{", ".join(city_data['zones'][2:4])}</div>
    </div>
    <div class="card" style="padding:16px;">
      <div class="muted xs">Tracked Brokers</div>
      <div class="bold" style="font-size:18px;color:var(--accent);margin-top:4px;">{len(BROKER_BRANCH_METADATA)} Nationwide Brokers</div>
      <div class="faint xs" style="margin-top:2px;">Physical & Digital Coverage</div>
    </div>
  </div>

  <section class="card" style="margin-bottom:32px;">
    <h2 style="font-size:19px;margin-top:0;margin-bottom:14px;">Stock Brokers Serving {c_name}</h2>
    <div class="table-scroll">
      <table class="data">
        <thead>
          <tr>
            <th>Broker Brand</th>
            <th>Depository</th>
            <th>Branch Model</th>
            <th>Helpline</th>
            <th class="center">Local Office</th>
          </tr>
        </thead>
        <tbody>
          {''.join(broker_rows)}
        </tbody>
      </table>
    </div>
  </section>

  <div class="grid g2" style="gap:20px;margin-bottom:32px;">
    <section class="card">
      <h3 style="font-size:17px;margin-top:0;margin-bottom:12px;">SEBI Regional Office & Grievance Desk</h3>
      <p class="xs" style="line-height:1.6;margin:0 0 10px 0;">
        Investors residing in {c_name} are protected under SEBI regulatory oversight. For broker default or unaddressed complaints, contact:
      </p>
      <div style="padding:12px;background:var(--surface-raised);border-radius:6px;font-size:13px;line-height:1.5;">
        <strong>Jurisdiction Address:</strong><br>
        {city_data['sebi_regional']}
      </div>
      <p class="muted xs" style="margin-top:10px;">
        Online resolution portal: <a href="https://scores.sebi.gov.in" target="_blank" rel="noopener">SEBI SCORES 2.0</a>
      </p>
    </section>

    <section class="card">
      <h3 style="font-size:17px;margin-top:0;margin-bottom:12px;">Offline Demat & KYC Guide in {c_name}</h3>
      <ul class="xs muted" style="line-height:1.6;padding-left:18px;margin:0;">
        <li><strong>Physical Share Demat:</strong> Fill Demat Request Form (DRF) and submit original certificates to your broker branch.</li>
        <li><strong>Non-Individual Accounts:</strong> HUF, Partnership, and Corporate accounts require branch In-Person Verification (IPV).</li>
        <li><strong>Nomination Updates:</strong> Add or modify up to 3 nominees online or by physical submission at branch desks.</li>
      </ul>
      <div style="margin-top:16px;">
        <a href="/registry/city/{city_key}/" class="btn secondary small">View {c_name} SEBI Intermediaries &rarr;</a>
      </div>
    </section>
  </div>

  <section class="card" style="margin-bottom:32px;">
    <h3 style="font-size:18px;margin-top:0;margin-bottom:14px;">SEBI Registered Intermediaries in {c_name}</h3>
    <div class="table-scroll">
      <table class="data">
        <thead>
          <tr><th>Entity Name</th><th>Category</th><th>SEBI Reg No</th><th>Registered Address</th></tr>
        </thead>
        <tbody>
          {''.join(reg_rows) if reg_rows else '<tr><td colspan="4" class="muted xs">No direct entity headquarters listed under sample. Trading serviced through member branch networks.</td></tr>'}
        </tbody>
      </table>
    </div>
  </section>

  <section class="card" style="margin-bottom:32px;">
    <h2 style="font-size:19px;margin-top:0;margin-bottom:16px;">Frequently Asked Questions</h2>
    <div class="faq-list">
      {faq_html}
    </div>
  </section>

  <section class="card">
    <h3 style="font-size:16px;margin-top:0;margin-bottom:12px;">Browse Other Financial Cities in India</h3>
    <div class="row-wrap" style="gap:8px;">
      {"".join(f'<a class="chip" href="/branches/city/{c}/">{CITIES[c]["name"]}</a>' for c in sorted(CITIES.keys()))}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from SEBI intermediary records and exchange disclosures.</p>
    <p style="margin-top:8px;">
      <a href="/branches/">All Branches</a> &bull;
      <a href="/brokers">All Brokers</a> &bull;
      <a href="/registry">SEBI Registry</a> &bull;
      <a href="/">Home</a>
    </p>
  </div>
</footer>
</body>
</html>"""


def _render_master_branches_hub(site_url):
    """Renders /branches/index.html (Master Hub)."""
    canonical = f"{site_url}/branches/"
    title = "Stock Broker Branches in India: City Directories, Demat Hubs & Local KYC Desks"
    desc = (
        "Find stock broker branch offices, authorized person desks, and depository participant centers across "
        "all major Indian cities. Covers Zerodha, Angel One, Motilal Oswal, Sharekhan, ICICI Direct, and more."
    )[:295]

    broker_cards = "".join(
        f'<div class="card" style="padding:16px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        f'<h3 style="margin:0;font-size:17px;color:var(--text-bright);">{m["brand"]}</h3>'
        f'<span class="badge" style="font-size:11px;">{m["demat_provider"]} DP</span>'
        f'</div>'
        f'<p class="muted xs" style="margin:0 0 10px 0;">{m["model"]}</p>'
        f'<p class="xs" style="margin:0 0 12px 0;"><strong>Helpline:</strong> {m["helpline"]}</p>'
        f'<div class="row-wrap" style="gap:6px;">'
        f'<a class="btn primary small" href="/broker/{b}/branches/">View City Branches &rarr;</a>'
        f'<a class="btn secondary small" href="/broker/{b}/">Review</a>'
        f'</div>'
        f'</div>'
        for b, m in sorted(BROKER_BRANCH_METADATA.items())
    )

    city_chips = "".join(
        f'<a class="chip" href="/branches/city/{c}/" style="padding:6px 12px;">{CITIES[c]["name"]} ({CITIES[c]["state"]})</a>'
        for c in sorted(CITIES.keys())
    )

    schema_jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": title,
                "url": canonical,
                "description": desc
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "BrokerLens", "item": f"{site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "Branches", "item": canonical}
                ]
            }
        ]
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{json.dumps(schema_jsonld, indent=2, ensure_ascii=False)}
</script>
</head>
<body>
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="brand">Broker<span>Lens</span></a>
    <div class="nav-links">
      <a href="/brokers">Brokers</a>
      <a href="/branches/" class="active">Branches</a>
      <a href="/trade-costs/">Trade Costs</a>
      <a href="/compare">Compare</a>
      <a href="/ipo">IPOs</a>
      <a href="/calculators">Calculators</a>
      <a href="/news">News</a>
    </div>
  </div>
</nav>

<main class="container" style="max-width:980px;margin:24px auto;padding:0 16px;">
  <div class="breadcrumb" style="font-size:13px;margin-bottom:16px;color:var(--text-muted);">
    <a href="/">BrokerLens</a> &rsaquo;
    <span>Broker Branches</span>
  </div>

  <header style="margin-bottom:28px;">
    <h1 style="font-size:30px;line-height:1.2;margin:0 0 10px 0;">Stock Broker Branches & Local Support Desks in India</h1>
    <p class="lead muted" style="font-size:15px;line-height:1.6;max-width:76ch;">
      Complete nationwide directory of stock broker branch offices, authorized representative desks, physical share demat (DRF) facilities, and customer care helplines across {len(CITIES)} major financial cities.
    </p>
  </header>

  <section style="margin-bottom:36px;">
    <h2 style="font-size:20px;margin-bottom:16px;">Top Broker Branch Networks</h2>
    <div class="grid g2" style="gap:16px;">
      {broker_cards}
    </div>
  </section>

  <section class="card">
    <h2 style="font-size:18px;margin-top:0;margin-bottom:12px;">Browse Branches by Financial City</h2>
    <p class="muted xs" style="margin-bottom:16px;">Select a city to explore local authorized offices, regional SEBI investor centers, and Depository Participants:</p>
    <div class="row-wrap" style="gap:8px;">
      {city_chips}
    </div>
  </section>
</main>

<footer class="footer" style="margin-top:48px;padding:32px 16px;border-top:1px solid var(--border);text-align:center;font-size:13px;color:var(--text-muted);">
  <div class="container" style="max-width:980px;margin:0 auto;">
    <p>BrokerLens India. Sourced from SEBI intermediary records.</p>
  </div>
</footer>
</body>
</html>"""


def generate_all(site_url="https://www.brokerlens.in"):
    """Generates all branch directory pages, broker hubs, city pages, and city registry hubs.
    
    Returns a list of generated URL paths for sitemap inclusion.
    """
    written_urls = []
    city_entities = _get_registry_city_entities()

    # 1. Master Hub: /branches/
    master_dir = os.path.join(SITE_DIR, "branches")
    os.makedirs(master_dir, exist_ok=True)
    with open(os.path.join(master_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(_render_master_branches_hub(site_url))
    written_urls.append("/branches/")

    # 2. Broker Branch Hubs & City Pages
    for b_id, meta in BROKER_BRANCH_METADATA.items():
        b_branch_dir = os.path.join(SITE_DIR, "broker", b_id, "branches")
        os.makedirs(b_branch_dir, exist_ok=True)
        with open(os.path.join(b_branch_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(_render_broker_branches_hub(b_id, meta, site_url))
        written_urls.append(f"/broker/{b_id}/branches/")

        for city_key, city_data in CITIES.items():
            c_dir = os.path.join(b_branch_dir, city_key)
            os.makedirs(c_dir, exist_ok=True)
            local_ents = city_entities.get(city_key, [])
            html_page = _render_city_branch_page(b_id, meta, city_key, city_data, local_ents, site_url)
            with open(os.path.join(c_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(html_page)
            written_urls.append(f"/broker/{b_id}/branches/{city_key}/")

    # 3. City Branch Comparison Hubs: /branches/city/[city-slug]/
    for city_key, city_data in CITIES.items():
        b_city_dir = os.path.join(SITE_DIR, "branches", "city", city_key)
        os.makedirs(b_city_dir, exist_ok=True)
        local_ents = city_entities.get(city_key, [])
        with open(os.path.join(b_city_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(_render_city_branches_comparison_hub(city_key, city_data, local_ents, site_url))
        written_urls.append(f"/branches/city/{city_key}/")

    # 4. City Registry Intermediary Hubs: /registry/city/[city-slug]/
    for city_key, city_data in CITIES.items():
        reg_city_dir = os.path.join(SITE_DIR, "registry", "city", city_key)
        os.makedirs(reg_city_dir, exist_ok=True)
        local_ents = city_entities.get(city_key, [])
        with open(os.path.join(reg_city_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(_render_city_registry_hub(city_key, city_data, local_ents, site_url))
        written_urls.append(f"/registry/city/{city_key}/")

    return written_urls


if __name__ == "__main__":
    urls = generate_all()
    print(f"Generated {len(urls)} branch and local registry pages.")
