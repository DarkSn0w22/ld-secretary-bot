"""
OWNDAYS L&D Org Structure — Thailand (อัพเดท 2026)
โครงสร้าง 8 Areas ใหม่ — ใช้เป็น single source of truth
import และใช้ใน system prompts ของทุก agent
"""

# ── 8 Areas with stores, SV/AM, and L&D staff ────────────────────────────────

AREAS = {
    "Area1": {
        "name": "Area 1",
        "sv_am": "SV Mink",
        "role": "Supervisor",
        "ld_staff": ["Trin", "Toy", "Milk"],
        "store_count": 10,
        "stores": [
            "Central Chiangmai(215)", "Central Rama 3(231)", "Central Hatyai(238)",
            "Central Ayutthaya(253)", "Central Chiangrai(268)",
            "V-Square Plaza Nakhon Sawan(283)", "Maya Chiangmai(300)",
            "Central Chiangmai Airport(7202)", "Central Phitsanulok(7211)",
            "CPN Lampang(7212)",
        ],
    },
    "Area2": {
        "name": "Area 2",
        "sv_am": "SV Meelap",
        "role": "Supervisor",
        "ld_staff": ["Kwang", "Tonpalm", "Benz"],
        "store_count": 10,
        "stores": [
            "Seacon Bangkae(205)", "Central Salaya(248)", "Central Samui(269)",
            "The Mall Bangkae(276)", "Central Westville(276)",
            "Central Nakhon Pathom(279)", "Robinson Ratchaburi(288)",
            "Robinson Lifestyle Kanchanaburi(291)",
            "Central Krabi(7204)", "Robinson Lifestyle Suphanburi(7210)",
        ],
    },
    "Area3": {
        "name": "Area 3",
        "sv_am": "SV Bow",
        "role": "Supervisor",
        "ld_staff": ["Kio", "Nueng", "Looklew"],
        "store_count": 9,
        "stores": [
            "Terminal 21 Pattaya(224)", "Central Rayong(240)", "Central Si Racha(252)",
            "Central Chanthaburi(256)", "Terminal 21 Rama 3(258)",
            "Central Nakhon Si(270)", "Charn At The Avenue(294)",
            "Robinson Lifestyle Chachoengsao(7201)", "New store-Prachinburi",
        ],
    },
    "Area4": {
        "name": "Area 4",
        "sv_am": "SV Ko",
        "role": "Supervisor",
        "ld_staff": ["Pui", "Mark"],
        "store_count": 10,
        "stores": [
            "Gaysorn Village Premium Store(216)", "Donki Mall Thonglor(230)",
            "Central Village(236)", "Siam Premium Outlets(243)",
            "Central Pinklao(249)", "Central Ramindra(266)",
            "Park Silom(272)", "True Digital Park(280)",
            "Robinson Latkrabang(296)", "New store-CPN Surattahni(7215)",
        ],
    },
    "Area5": {
        "name": "Area 5",
        "sv_am": "SV Juji",
        "role": "Supervisor",
        "ld_staff": ["Jajah", "Jets"],
        "store_count": 10,
        "stores": [
            "Central Eastville(204)", "Central Mahachai(218)",
            "Icon Siam(225)", "Gateway Bangsue(226)", "Central Rama 2(251)",
            "Marche Thonglor(271)", "Makro Sri Ayutthaya(284)",
            "One Bangkok(286)", "Esplanade Ratchada(292)", "Habbitat",
        ],
    },
    "Area6": {
        "name": "Area 6",
        "sv_am": "AM Chock",
        "role": "Area Manager",
        "ld_staff": ["Jib"],
        "store_count": 7,
        "stores": [
            "Mega Bangna(201)", "Fashion Island(209)", "Central Westgate(222)",
            "Central Rama 9(285)", "Lotus's Mall Makro Sathon(290)",
            "The Mall Bang Kapi(297)", "New store-Northville(7214)",
        ],
    },
    "Area7": {
        "name": "Area 7",
        "sv_am": "SV Champ",
        "role": "Supervisor",
        "ld_staff": ["Fair"],
        "store_count": 10,
        "stores": [
            "The Mall Korat(210)", "Central Udon(214)", "Central Phuket(220)",
            "Central Khonkaen(254)", "Market Village Huahin(289)",
            "Robinson Lifestyle Saraburi(293)",
            "Outlet Square Muang Thong Thani(7203)", "Robinson Lifestyle Trang(7205)",
            "Robinson Lifestyle Buriram(7207)", "CPN Khonkaen Campus(7213)",
        ],
    },
    "Area8": {
        "name": "Area 8",
        "sv_am": "AM Aom",
        "role": "Area Manager",
        "ld_staff": ["Judy"],
        "store_count": 8,
        "stores": [
            "Zpell @ Future Park(203)", "Seacon Square(206)", "CentralWorld(223)",
            "Siam Center(244)", "Imperial World Samrong(208)",
            "The Glass Market Bangna(7209)",
            "New store-Petchaburi", "New store-Chaengwattana",
        ],
    },
}

# ── L&D Staff roles & division ────────────────────────────────────────────────

LD_STAFF = {
    # Area 1
    "Trin":     {"area": "Area1", "title": "L&D Trainer",   "division": "Sales"},
    "Toy":      {"area": "Area1", "title": "L&D Trainer",   "division": "Optical"},
    "Milk":     {"area": "Area1", "title": "L&D Specialist", "division": "Optometry"},

    # Area 2
    "Kwang":    {"area": "Area2", "title": "L&D Trainer",   "division": "Optical"},
    "Tonpalm":  {"area": "Area2", "title": "L&D Trainer",   "division": "Sales"},
    "Benz":     {"area": "Area2", "title": "L&D Specialist", "division": "Optometry"},

    # Area 3
    "Kio":      {"area": "Area3", "title": "L&D Trainer",   "division": "Optical"},
    "Nueng":    {"area": "Area3", "title": "L&D Trainer",   "division": "Sales"},
    "Looklew":  {"area": "Area3", "title": "L&D Specialist", "division": "Optometry"},

    # Area 4
    "Pui":      {"area": "Area4", "title": "L&D Asst.Training Manager", "division": "Sales"},
    "Mark":     {"area": "Area4", "title": "L&D Trainer",   "division": "Optical"},

    # Area 5
    "Jajah":    {"area": "Area5", "title": "L&D Asst.Training Manager", "division": "Optical"},
    "Jets":     {"area": "Area5", "title": "L&D Trainer",   "division": "Sales"},

    # Area 6
    "Jib":      {"area": "Area6", "title": "L&D Training Manager Optical&Service", "division": "Optical"},

    # Area 7
    "Fair":     {"area": "Area7", "title": "L&D Specialist Optometry&Service", "division": "Optometry"},

    # Area 8
    "Judy":     {"area": "Area8", "title": "L&D Training Manager Sales&Service", "division": "Sales"},

    # Regional
    "Peanut":   {"area": "Regional", "title": "Regional L&D Manager", "division": "Regional"},
    "Jame":     {"area": "Regional", "title": "Regional L&D",         "division": "Regional"},
}

# ── Division mapping (Hybrid — trained at academy, deployed by area) ─────────

DIVISION = {
    "Sales":      ["Pui", "Jets", "Trin", "Nueng", "Tonpalm", "Judy"],
    "Optical":    ["Jib", "Jajah", "Kio", "Toy", "Kwang", "Mark"],
    "Optometry":  ["Fair", "Benz", "Milk", "Looklew"],
}

# ── Convenience: find area by store name/code ─────────────────────────────────

def find_area_by_store(store_name: str) -> str | None:
    """คืนชื่อ Area ที่สาขานั้นอยู่ เช่น 'Area1'"""
    name_lower = store_name.lower()
    for area_key, area in AREAS.items():
        for s in area["stores"]:
            if name_lower in s.lower():
                return area_key
    return None


def find_area_by_trainer(trainer_name: str) -> dict | None:
    """คืนข้อมูล area ของ trainer คนนั้น"""
    staff = LD_STAFF.get(trainer_name)
    if not staff:
        return None
    area_key = staff["area"]
    if area_key == "Regional":
        return {"name": "Regional", "sv_am": "Peanut/Jame"}
    area = AREAS.get(area_key, {})
    return {**area, "area_key": area_key, "trainer_info": staff}


def get_area_summary_text() -> str:
    """สรุป 8 Areas สำหรับใส่ใน system prompt"""
    lines = ["8 Areas (โครงสร้างใหม่ 2026):"]
    for key, a in AREAS.items():
        staff_str = ", ".join(a["ld_staff"])
        lines.append(
            f"  {a['name']} ({a['sv_am']}) — {a['store_count']} สาขา | L&D: {staff_str}"
        )
    return "\n".join(lines)


def get_area_stores_text() -> str:
    """รายชื่อสาขาทุก area สำหรับ Rex/Atlas"""
    lines = []
    for key, a in AREAS.items():
        stores = ", ".join(a["stores"])
        lines.append(f"{a['name']} ({a['sv_am']}): {stores}")
    return "\n".join(lines)
