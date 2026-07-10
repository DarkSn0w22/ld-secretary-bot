// ============================================================
// L&D Dashboard — GAS API v10 (v9 + Area source switch, Employee
// Management, Trainer tiers, Academy aggregator)
// ทั้งไฟล์นี้เป็นสำเนาไว้เทียบ/track การเปลี่ยนแปลง — ต้อง copy วางทับ
// ใน Google Apps Script editor แล้ว Deploy ใหม่เองด้วยนะครับ (ยังไม่มี clasp เชื่อมตรง)
//
// v10 changes:
//   - AREA_ID เปลี่ยนไปสเปรดชีตใหม่ (โครงสร้าง Area1-Area8 แทน MS/MT/NC/WN/SE เดิม)
//     getAreaData() เขียนใหม่ทั้งหมดให้ตรงกับ tab A{n}-Employee/-Store/-Learning
//     ชื่อ/หัวหน้างานต่อ Area อ้างตาม org_structure.py (single source of truth ของบอท)
//     หมายเหตุ: สเปรดชีตใหม่เพิ่งสร้าง ข้อมูล metric ยังเป็น 0 ทั้งหมด (template รอบ
//     รายงาน Jun-Nov 2026) เป็นเรื่องคาดหมายไว้แล้ว ไม่ใช่บั๊ก
//   - เพิ่ม action=employee — getEmployeeManagementData() ดึงจากไฟล์ Employee Master
//     เดียวกับ Assessment (ASSESS_ID) แต่คนละ tab: Employee, HQ, Resigned employee,
//     Training, Assessment + OAR ทั้ง 2 tab (Registrations + Registration (OBT))
//   - getSurveyData(): ตัดคำต่อท้าย "(Department)" ออกจากชื่อ trainer, แนบ tier
//     (head/asst/trainer) ตามรายชื่อ L&D จริงที่ปรากฏใน Main Trainer column
//   - เพิ่ม action=academy — getAcademyData() สรุปเลขหลักๆจากทุก action รวมไว้ที่เดียว
//   - เพิ่ม action=od_connect — getOdConnectData() ดึงสรุปการใช้งาน OD-Connect จาก
//     Google Analytics 4 (GA4 Data API) ตรงจาก Code.gs เอง ผ่าน ScriptApp.getOAuthToken()
//     (ตัวตนของคนที่ deploy สคริปต์นี้ — ไม่ต้องมี service account/key แยก ดูวิธี
//     setup ในคอมเมนต์เหนือ getOdConnectData). ไม่รวมอยู่ใน action=all เพราะเป็น
//     external API call ที่หนักกว่าปกติ — ให้ frontend ดึงเฉพาะตอนเปิด tab นี้เท่านั้น
// ============================================================
var SURVEY_ID    = "1RlnQEXOJ3EPwqnuDLMk3rjBvinJbW1wKFcRyMfdlEVs";
var DASHBOARD_ID = "1QKjyFlmJrgmiYHagn7olhpr41ucQJQc8ck3zae8obJI";
var OAR_ID       = "1Ux83yvg3sdANd8_OB104Np9jartOfEF9_xhoX5JslSU";
var AREA_ID      = "1Yb5CFwZDp9nF0M7NUhjo3hulS_GNZelG";
var ASSESS_ID    = "1FLIugt_XASi_vsP7FHdL2UVthQQDsdZpH6St3zVofMU"; // = Employee Master ทั้งไฟล์ (Employee/HQ/Resigned employee/Training/Assessment)
var GA4_PROPERTY_ID = "539554359"; // จาก analytics.google.com/analytics/web/#/a268231845p539554359

var RATING_MAP = {"Very good":4,"Good":3,"Quite Good":2,"Moderate":1,"Needs Improvement":0};

function doGet(e) {
  var p = (e && e.parameter) || {};
  var cb = p.callback || "";
  var year = p.year || "";
  var out;
  try {
    var act = p.action || "all";
    if (act === "all") {
      out = {status:"success", timestamp:new Date().toISOString(), year:year, survey:getSurveyData(year), cost:getCostData(year), asset:getAssetData(), oar:getOarData(year), area:getAreaData(), assessment:getAssessmentData(), employee:getEmployeeManagementData(), academy:getAcademyData()};
    } else if (act === "survey") {
      out = getSurveyData(year);
    } else if (act === "cost") {
      out = getCostData(year);
    } else if (act === "asset") {
      out = getAssetData();
    } else if (act === "oar") {
      out = getOarData(year);
    } else if (act === "area") {
      out = getAreaData();
    } else if (act === "assessment") {
      out = getAssessmentData();
    } else if (act === "employee") {
      out = getEmployeeManagementData();
    } else if (act === "academy") {
      out = getAcademyData();
    } else if (act === "od_connect") {
      out = getOdConnectData(p.days ? parseInt(p.days, 10) : 28);
    } else if (act === "ping") {
      out = {status:"success", message:"pong", timestamp:new Date().toISOString()};
    } else {
      out = {status:"error", message:"Unknown action"};
    }
  } catch(err) {
    out = {status:"error", message:err.toString()};
  }
  var json = JSON.stringify(out);
  if (cb) {
    return ContentService.createTextOutput(cb + "(" + json + ")").setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);
}

// ============================================================
// SURVEY
// ============================================================
function getSurveyData(year) {
  // --- inline helpers ---
  function _r2(n) { return Math.round(n * 100) / 100; }
  function _za(n) { var a = []; for (var i = 0; i < n; i++) a.push(0); return a; }
  function _colIdx(hdr, kw) { for (var i = 0; i < hdr.length; i++) { if (String(hdr[i]).indexOf(kw) >= 0) return i; } return -1; }
  // --- end helpers ---

  var ss;
  try { ss = SpreadsheetApp.openById(SURVEY_ID); }
  catch(e) { return {status:"error", message:"Cannot open Survey: " + e}; }

  var sheets = ss.getSheets();
  var allCourses = {}, monthly = {}, trainerStats = {};
  var totalR = 0, totalS = 0;

  for (var s = 0; s < sheets.length; s++) {
    var sh = sheets[s], nm = sh.getName();
    if (nm === "All Responses") continue;
    var data = sh.getDataRange().getValues();
    if (data.length < 2) continue;
    var hdr = data[0];
    var tsC = _colIdx(hdr, "Timestamp");
    if (tsC < 0) continue;
    var trC = _colIdx(hdr, "Main Trainer");
    var rCols = [];
    for (var h = 0; h < hdr.length; h++) {
      if (String(hdr[h]).match(/^[12345]\./)) rCols.push(h);
    }

    var tS = _za(10), tN = _za(10), tV = _za(10);
    var cSum = 0, cR = 0;

    for (var r = 1; r < data.length; r++) {
      var row = data[r];
      if (!row[tsC]) continue;

      var ts = String(row[tsC]), mk = "", rowYear = "";
      if (ts.match(/^\d{4}-\d{2}/)) {
        mk = ts.substring(0, 7);
        rowYear = ts.substring(0, 4);
      } else {
        try {
          var d = new Date(row[tsC]);
          if (!isNaN(d.getTime())) {
            mk = Utilities.formatDate(d, "Asia/Bangkok", "yyyy-MM");
            rowYear = Utilities.formatDate(d, "Asia/Bangkok", "yyyy");
          }
        } catch(ex) {}
      }

      if (year && rowYear && rowYear !== year) continue;

      cR++; totalR++;

      if (mk) {
        if (!monthly[mk]) monthly[mk] = {};
        monthly[mk][nm] = (monthly[mk][nm] || 0) + 1;
        monthly[mk]["total"] = (monthly[mk]["total"] || 0) + 1;
      }

      var rs = 0, rc = 0;
      for (var ri = 0; ri < rCols.length && ri < 10; ri++) {
        var sc = RATING_MAP[String(row[rCols[ri]])];
        if (sc !== undefined) { tS[ri] += sc; tN[ri]++; if (sc === 4) tV[ri]++; rs += sc; rc++; }
      }
      if (rc > 0) cSum += rs / rc;

      if (trC >= 0 && row[trC]) {
        // ตัดคำต่อท้าย "(Department)" ออก เช่น "Jets (Sales & Service)" -> name="Jets", dept="Sales & Service"
        var tnRaw = String(row[trC]).trim();
        var tnMatch = tnRaw.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
        var tn = tnMatch ? tnMatch[1].trim() : tnRaw;
        var dept = tnMatch ? tnMatch[2].trim() : "";
        if (tn) {
          if (!trainerStats[tn]) trainerStats[tn] = {ts: 0, c: 0, cs: {}, dept: dept};
          if (dept && !trainerStats[tn].dept) trainerStats[tn].dept = dept;
          if (rc > 0) {
            trainerStats[tn].ts += rs / rc;
            trainerStats[tn].c++;
            trainerStats[tn].cs[nm] = (trainerStats[tn].cs[nm] || 0) + 1;
          }
        }
      }
    }

    if (cR > 0) {
      var ta = [], tv = [];
      for (var i = 0; i < 10; i++) {
        ta.push(tN[i] ? _r2(tS[i] / tN[i]) : 0);
        tv.push(tN[i] ? Math.round(tV[i] / tN[i] * 100) : 0);
      }
      allCourses[nm] = {responses: cR, avg: _r2(cSum / cR), topic_avgs: ta, topic_vg: tv};
      totalS += cSum;
    }
  }

  // L&D leadership tier — รายชื่อจริงตาม org_structure.py (single source of truth ของบอท)
  // หัวหน้า/ผู้จัดการ เทรนน้อยกว่าน้องๆทีมเป็นปกติ เพราะงานหลักคือบริหาร ไม่ใช่สอนเอง
  var TIER_HEAD = ["Peanut", "Jame", "Judy", "Jib", "Fair"];
  var TIER_ASST = ["Pui", "Jajah", "Jajh"]; // เผื่อสะกดต่างกันในชีตจริง
  function _trainerTier(name) {
    if (TIER_HEAD.indexOf(name) >= 0) return "head";
    if (TIER_ASST.indexOf(name) >= 0) return "asst";
    return "trainer";
  }

  var trR = [];
  for (var k in trainerStats) {
    var t = trainerStats[k];
    trR.push({
      name: k, avg: t.c ? _r2(t.ts / t.c) : 0, count: t.c, courses: t.cs,
      department: t.dept || "", tier: _trainerTier(k),
      kpi_score: null // placeholder — จะมีค่าจริงตอนเชื่อม sheet ประเมิน KPI ในอนาคต
    });
  }
  trR.sort(function(a, b) { return b.avg - a.avg; });

  return {
    status: "success",
    year: year || "all",
    courses: allCourses,
    monthly: monthly,
    total_responses: totalR,
    overall_avg: totalR ? _r2(totalS / totalR) : 0,
    trainers: trR
  };
}

// ============================================================
// COST  (v9: tab จริงคือ "L&D Financial")
// ============================================================
function getCostData(year) {
  // --- inline helpers ---
  function _r2(n) { return Math.round(n * 100) / 100; }
  function _za(n) { var a = []; for (var i = 0; i < n; i++) a.push(0); return a; }
  function _pNum(v) {
    if (v === null || v === undefined || v === "") return 0;
    if (typeof v === "number") return v;
    var s = String(v).replace(/[฿$,\s]/g, "").trim();
    var n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  }
  function _scanRight(row, fromCol) {
    for (var c = fromCol + 1; c < Math.min(fromCol + 6, row.length); c++) {
      var v = _pNum(row[c]);
      if (v > 0) return v;
    }
    return 0;
  }
  function _rowToString(row) {
    var s = "";
    for (var c = 0; c < row.length; c++) s += String(row[c]).toLowerCase() + " ";
    return s;
  }
  function _findSheet(ss, kw) {
    var sheets = ss.getSheets();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getName().indexOf(kw) >= 0) return sheets[i];
    }
    return null;
  }
  // --- end helpers ---

  var ss;
  try { ss = SpreadsheetApp.openById(DASHBOARD_ID); }
  catch(e) { return {status:"error", message:"Cannot open: " + e}; }

  var sheet = null;
  if (year) {
    sheet = _findSheet(ss, "L&D Financial " + year) || _findSheet(ss, year + " L&D Financial");
  }
  if (!sheet) sheet = _findSheet(ss, "L&D Financial");
  if (!sheet) sheet = _findSheet(ss, "Cost"); // fallback เผื่อชื่อ tab เปลี่ยนกลับในอนาคต
  if (!sheet) {
    var sheetNames = ss.getSheets().map(function(s){ return s.getName(); });
    return {status:"error", message:"Cost sheet not found. Available sheets: " + sheetNames.join(", ")};
  }

  var data = sheet.getDataRange().getValues();
  var totalBudget = 0, totalActual = 0, totalBalance = 0, avgPerEmployee = 0;

  for (var r = 0; r < Math.min(10, data.length); r++) {
    for (var c = 0; c < data[r].length; c++) {
      var cv = String(data[r][c]);
      if (cv.indexOf("Total L&D Budget") >= 0) totalBudget = _scanRight(data[r], c);
      if (cv === "Actual expenses" && r < 6) totalActual = _scanRight(data[r], c);
      if (cv === "Balance" && r < 8) totalBalance = _scanRight(data[r], c);
      if (cv.indexOf("AVG Per Employee") >= 0) {
        if (r + 1 < data.length) {
          for (var sc2 = Math.max(0, c - 1); sc2 < Math.min(c + 3, data[r + 1].length); sc2++) {
            var vv = _pNum(data[r + 1][sc2]);
            if (vv > 0) { avgPerEmployee = vv; break; }
          }
        }
        if (avgPerEmployee === 0) avgPerEmployee = _scanRight(data[r], c);
      }
    }
  }

  var monthlyData = _za(12);
  for (var r3 = 0; r3 < data.length; r3++) {
    if (String(data[r3][1]).indexOf("Actual Monthly Expenses") >= 0 && r3 + 1 < data.length) {
      for (var mc = 0; mc < 12; mc++) monthlyData[mc] = _pNum(data[r3 + 1][mc + 2]) || 0;
      break;
    }
  }

  var catDefs = [
    {keywords: ["OWNDAYS Connect"], name: "OD Connect Service"},
    {keywords: ["internal Dev", "L&D internal"], name: "Internal Dev & Support"},
    {keywords: ["Training Digital", "recognition rewards"], name: "Training Digital & Rewards"},
    {keywords: ["Oversea Transport"], name: "Oversea Transport"},
    {keywords: ["L&D TH Transport", "TH Transportat"], name: "TH Transport"}
  ];

  var categories = [];
  for (var ci = 0; ci < catDefs.length; ci++) {
    var cat = catDefs[ci];
    var catBudget = 0, catActual = 0;
    var foundRow = -1;

    for (var sr = 0; sr < data.length; sr++) {
      var rowStr = _rowToString(data[sr]);
      for (var ki = 0; ki < cat.keywords.length; ki++) {
        if (rowStr.indexOf(cat.keywords[ki].toLowerCase()) >= 0) { foundRow = sr; break; }
      }
      if (foundRow >= 0) break;
    }

    if (foundRow >= 0) {
      for (var lr = foundRow; lr < Math.min(foundRow + 4, data.length); lr++) {
        for (var lc = 0; lc < data[lr].length; lc++) {
          var cellStr = String(data[lr][lc]).trim();
          if (cellStr.indexOf("Total Budget") >= 0 || cellStr.indexOf("Total all area Budget") >= 0) catBudget = _scanRight(data[lr], lc);
          if (cellStr === "Actual expenses") catActual = _scanRight(data[lr], lc);
        }
      }
    }

    var pct = catBudget > 0 ? _r2((catActual / catBudget) * 100) : 0;
    categories.push({name: cat.name, budget: catBudget, actual: catActual, balance: catBudget - catActual, pct: pct});
  }

  return {
    status: "success",
    year: year || "current",
    budget: totalBudget,
    actual: totalActual,
    balance: totalBalance,
    avg_per_employee: avgPerEmployee,
    categories: categories,
    monthly: {labels: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], data: monthlyData}
  };
}

// ============================================================
// ASSET
// ============================================================
function getAssetData() {
  // --- inline helpers ---
  function _findSheet(ss, kw) {
    var sheets = ss.getSheets();
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getName().indexOf(kw) >= 0) return sheets[i];
    }
    return null;
  }
  // --- end helpers ---

  var ss;
  try { ss = SpreadsheetApp.openById(DASHBOARD_ID); }
  catch(e) { return {status:"error", message:"Cannot open: " + e}; }

  var sheet = _findSheet(ss, "Asset");
  if (!sheet) return {status:"error", message:"Asset sheet not found"};

  var data = sheet.getDataRange().getValues();
  var laptops = [], ipads = [], sec = "";

  for (var r = 0; r < data.length; r++) {
    var f = String(data[r][0]).trim().toLowerCase();
    if (f === "laptop") { sec = "laptop"; continue; }
    if (f === "ipad") { sec = "ipad"; continue; }
    if (f === "brand") continue;
    if (!data[r][0] || String(data[r][0]).trim() === "") continue;

    if (sec === "laptop") {
      laptops.push({
        brand: String(data[r][0]).trim().toUpperCase(),
        model: String(data[r][1] || "").trim(),
        serial: String(data[r][2] || "").trim(),
        code: String(data[r][3] || "—").trim(),
        owner: String(data[r][4] || "").trim(),
        nickname: String(data[r][5] || "").trim(),
        status: String(data[r][8] || "Normal").trim()
      });
    }
    if (sec === "ipad") {
      ipads.push({
        model: String(data[r][1] || "").trim(),
        serial: String(data[r][2] || "").trim(),
        code: String(data[r][3] || "—").trim(),
        owner: String(data[r][4] || "").trim(),
        nickname: String(data[r][5] || "").trim(),
        status: String(data[r][8] || "Normal").trim()
      });
    }
  }

  var norm = laptops.filter(function(l) { return l.status === "Normal"; }).length;
  return {
    status: "success",
    laptops: laptops,
    ipads: ipads,
    total_laptops: laptops.length,
    total_ipads: ipads.length,
    normal: norm + ipads.length,
    issues: laptops.length - norm
  };
}

// ============================================================
// OAR — Training Registration Data
// ============================================================
function getOarData(year) {
  var ss;
  try { ss = SpreadsheetApp.openById(OAR_ID); }
  catch(e) { return {status:"error", message:"Cannot open OAR: " + e}; }

  var sheet = ss.getSheetByName("Registrations");
  if (!sheet) {
    var sheets = ss.getSheets();
    if (sheets.length > 0) sheet = sheets[0];
    else return {status:"error", message:"No sheets found in OAR"};
  }

  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return {status:"success", total:0, courses:{}, branches:{}, matrix:{}};

  var hdr = data[0];
  var colTS = -1, colBranch = -1, colTopic = -1, colDate = -1;
  for (var i = 0; i < hdr.length; i++) {
    var h = String(hdr[i]).trim().toLowerCase();
    if (h === "timestamp") colTS = i;
    if (h === "branch") colBranch = i;
    if (h === "training topic") colTopic = i;
    if (h === "training date") colDate = i;
  }

  if (colTopic < 0) return {status:"error", message:"Training Topic column not found"};

  var courses = {};
  var branches = {};
  var matrix = {};
  var total = 0;

  for (var r = 1; r < data.length; r++) {
    var row = data[r];

    if (year) {
      var rowYear = "";
      var dateVal = colDate >= 0 ? row[colDate] : null;
      var tsVal = colTS >= 0 ? row[colTS] : null;

      if (dateVal) {
        var ds = String(dateVal);
        if (ds.match(/^\d{4}/)) {
          rowYear = ds.substring(0, 4);
        } else {
          try {
            var dd = new Date(dateVal);
            if (!isNaN(dd.getTime())) rowYear = Utilities.formatDate(dd, "Asia/Bangkok", "yyyy");
          } catch(ex) {}
        }
      }
      if (!rowYear && tsVal) {
        try {
          var dt = new Date(tsVal);
          if (!isNaN(dt.getTime())) rowYear = Utilities.formatDate(dt, "Asia/Bangkok", "yyyy");
        } catch(ex2) {}
      }

      if (rowYear && rowYear !== year) continue;
    }

    var topic = colTopic >= 0 ? String(row[colTopic]).trim() : "";
    var branch = colBranch >= 0 ? String(row[colBranch]).trim() : "";

    if (!topic) continue;

    var parts = topic.split(/\s+/);
    var code = parts[parts.length - 1];
    if (code.length > 6) code = topic;

    total++;
    courses[code] = (courses[code] || 0) + 1;

    if (branch) {
      branches[branch] = (branches[branch] || 0) + 1;
      if (!matrix[branch]) matrix[branch] = {};
      matrix[branch][code] = (matrix[branch][code] || 0) + 1;
    }
  }

  return {
    status: "success",
    year: year || "all",
    total: total,
    courses: courses,
    branches: branches,
    matrix: matrix
  };
}

// ============================================================
// AREA — Area Performance Data (v10: โครงสร้าง Area1-Area8 ใหม่)
// ชื่อ/หัวหน้างาน/L&D staff ต่อ area อ้างตาม org_structure.py ของบอท (single source of truth)
// หมายเหตุ: สเปรดชีตนี้เพิ่งสร้างใหม่สำหรับรอบรายงาน Jun-Nov 2026 — คอลัมน์ identity
// (branch/name/position ฯลฯ) มีข้อมูลแล้ว แต่ตัวเลข performance ส่วนใหญ่ยังเป็น 0
// จนกว่าทีม L&D จะกรอกข้อมูลรายเดือน — ไม่ใช่บั๊ก เป็นเรื่องคาดหมายไว้แล้ว
// ============================================================
function getAreaData() {
  // --- inline helpers ---
  function _r2(n) { return Math.round(n * 100) / 100; }
  function _pNum(v) {
    if (v === null || v === undefined || v === "") return 0;
    if (typeof v === "number") return v;
    var s = String(v).replace(/[฿$,\s%]/g, "").trim();
    var n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  }
  function _colIdx(hdr, kw) {
    for (var i = 0; i < hdr.length; i++) {
      var h = String(hdr[i]).replace(/\n/g, " ").trim();
      if (h.indexOf(kw) >= 0) return i;
    }
    return -1;
  }
  // --- end helpers ---

  var ss;
  try { ss = SpreadsheetApp.openById(AREA_ID); }
  catch(e) { return {status:"error", message:"Cannot open Area sheet: " + e}; }

  var AREA_MAP = {
    "Area1": {name: "Area 1", svAm: "SV Mink",   ldStaff: ["Trin","Toy","Milk"],       empSheet: "A1-Employee", storeSheet: "A1-Store", learnSheet: "A1-Learning"},
    "Area2": {name: "Area 2", svAm: "SV Meelap",  ldStaff: ["Kwang","Tonpalm","Benz"],  empSheet: "A2-Employee", storeSheet: "A2-Store", learnSheet: "A2-Learning"},
    "Area3": {name: "Area 3", svAm: "SV Bow",     ldStaff: ["Kio","Nueng","Looklew"],   empSheet: "A3-Employee", storeSheet: "A3-Store", learnSheet: "A3-Learning"},
    "Area4": {name: "Area 4", svAm: "SV Ko",      ldStaff: ["Pui","Mark"],              empSheet: "A4-Employee", storeSheet: "A4-Store", learnSheet: "A4-Learning"},
    "Area5": {name: "Area 5", svAm: "SV Juji",    ldStaff: ["Jajah","Jets"],            empSheet: "A5-Employee", storeSheet: "A5-Store", learnSheet: "A5-Learning"},
    "Area6": {name: "Area 6", svAm: "AM Chock",   ldStaff: ["Jib"],                     empSheet: "A6-Employee", storeSheet: "A6-Store", learnSheet: "A6-Learning"},
    "Area7": {name: "Area 7", svAm: "SV Champ",   ldStaff: ["Fair"],                    empSheet: "A7-Employee", storeSheet: "A7-Store", learnSheet: "A7-Learning"},
    "Area8": {name: "Area 8", svAm: "AM Aom",     ldStaff: ["Judy"],                    empSheet: "A8-Employee", storeSheet: "A8-Store", learnSheet: "A8-Learning"}
  };

  var result = {status: "success", areas: {}};

  for (var areaCode in AREA_MAP) {
    var cfg = AREA_MAP[areaCode];
    var areaResult = {
      name: cfg.name, sv_am: cfg.svAm, ld_staff: cfg.ldStaff,
      employee_summary: {}, store_summary: {}, learning_summary: {}
    };

    // === EMPLOYEE SHEET ===
    try {
      var empSh = ss.getSheetByName(cfg.empSheet);
      if (empSh) {
        var empData = empSh.getDataRange().getValues();
        var empHdrRow = -1;
        for (var r = 0; r < Math.min(5, empData.length); r++) {
          if (String(empData[r][0]).trim() === "Branch") { empHdrRow = r; break; }
        }
        if (empHdrRow >= 0) {
          var empHdr = empData[empHdrRow];
          var cGrade = _colIdx(empHdr, "Grade");
          var cProb = _colIdx(empHdr, "Probation Status");
          var cObt = _colIdx(empHdr, "OBT Status");
          var cTalent = _colIdx(empHdr, "Talent");
          var cNextCourse = _colIdx(empHdr, "Next Course");

          var total = 0, probation = 0, confirmed = 0;
          var obtPass = 0, obtProg = 0, obtNot = 0;
          var g1 = 0, g2 = 0, g3 = 0, evalGap = 0, talentCount = 0, needsNextCourse = 0;

          for (var r2 = empHdrRow + 1; r2 < empData.length; r2++) {
            var row = empData[r2];
            if (!row[0] || String(row[0]).trim() === "") continue;
            total++;

            if (cProb >= 0) {
              var ps = String(row[cProb]).trim();
              if (ps === "Confirmed") confirmed++;
              else probation++;
            }

            if (cObt >= 0) {
              var os = String(row[cObt]).trim();
              if (os === "Pass") obtPass++;
              else if (os.indexOf("Progress") >= 0) obtProg++;
              else obtNot++;
            }

            if (cGrade >= 0) {
              var gr = String(row[cGrade]).trim();
              if (gr === "1st") g1++;
              else if (gr === "2nd") g2++;
              else if (gr === "3rd") g3++;
            }

            if (cTalent >= 0) {
              var tl = String(row[cTalent]).trim().toUpperCase();
              if (tl === "Y" || tl === "YES") talentCount++;
            }
            if (cNextCourse >= 0 && String(row[cNextCourse]).trim()) needsNextCourse++;
          }
          evalGap = total - (g1 + g2 + g3);
          if (evalGap < 0) evalGap = 0;

          areaResult.employee_summary = {
            total: total, probation: probation, confirmed: confirmed,
            obt_pass: obtPass, obt_in_progress: obtProg, obt_not_started: obtNot,
            grade_1st: g1, grade_2nd: g2, grade_3rd: g3, eval_gap: evalGap,
            talent_count: talentCount, needs_next_course: needsNextCourse
          };
        }
      }
    } catch(ex) { areaResult.employee_summary = {error: ex.toString()}; }

    // === STORE SHEET ===
    try {
      var stSh = ss.getSheetByName(cfg.storeSheet);
      if (stSh) {
        var stData = stSh.getDataRange().getValues();
        var stHdrRow = -1;
        for (var r3 = 0; r3 < Math.min(5, stData.length); r3++) {
          if (String(stData[r3][0]).trim() === "Month") { stHdrRow = r3; break; }
        }
        if (stHdrRow >= 0) {
          var stHdr = stData[stHdrRow];
          var cTopup = _colIdx(stHdr, "Top-up");
          var cNps = _colIdx(stHdr, "NPS");
          var cAcc = _colIdx(stHdr, "Accuracy");
          var cSelfEye = _colIdx(stHdr, "Self Eye-test");
          var cClRev = _colIdx(stHdr, "CL Revenue");
          var cSalesAvg = _colIdx(stHdr, "Sales Avg");
          var cTotalSale = _colIdx(stHdr, "Total Sale");
          var cSalesAch = _colIdx(stHdr, "Sales Achievement");
          var cComplaint = _colIdx(stHdr, "Complaint");
          var cRedFlag = _colIdx(stHdr, "Red Flag");

          var sumTopup = 0, sumNps = 0, sumAcc = 0, sumSelf = 0, sumClRev = 0;
          var sumSalesAvg = 0, sumSalesAch = 0, sumTotalSale = 0, sumComplaints = 0, sumRedFlags = 0;
          var nTopup = 0, nNps = 0, nAcc = 0, nSelf = 0, nClRev = 0, nSalesAvg = 0, nSalesAch = 0, stRows = 0;

          for (var r4 = stHdrRow + 1; r4 < stData.length; r4++) {
            var srow = stData[r4];
            if (!srow[0] || String(srow[0]).trim() === "") continue;
            stRows++;

            if (cTopup >= 0) { var vt = _pNum(srow[cTopup]); if (vt > 0) { sumTopup += vt; nTopup++; } }
            if (cNps >= 0) { var vn = _pNum(srow[cNps]); if (vn > 0) { sumNps += vn; nNps++; } }
            if (cAcc >= 0) { var va = _pNum(srow[cAcc]); if (va > 0) { sumAcc += va; nAcc++; } }
            if (cSelfEye >= 0) { var vs = _pNum(srow[cSelfEye]); if (vs > 0) { sumSelf += vs; nSelf++; } }
            if (cClRev >= 0) { var vc = _pNum(srow[cClRev]); if (vc > 0) { sumClRev += vc; nClRev++; } }
            if (cSalesAvg >= 0) { var vsa = _pNum(srow[cSalesAvg]); if (vsa > 0) { sumSalesAvg += vsa; nSalesAvg++; } }
            if (cSalesAch >= 0) { var vac = _pNum(srow[cSalesAch]); if (vac > 0) { sumSalesAch += vac; nSalesAch++; } }
            if (cTotalSale >= 0) { sumTotalSale += _pNum(srow[cTotalSale]); }
            if (cComplaint >= 0) { sumComplaints += _pNum(srow[cComplaint]); }
            if (cRedFlag >= 0) {
              var rf = String(srow[cRedFlag]).trim().toUpperCase();
              if (rf === "Y" || rf === "YES") sumRedFlags++;
            }
          }

          areaResult.store_summary = {
            rows: stRows,
            avg_topup: nTopup ? _r2(sumTopup / nTopup) : 0,
            avg_nps: nNps ? _r2(sumNps / nNps) : 0,
            avg_accuracy: nAcc ? _r2(sumAcc / nAcc) : 0,
            avg_self_eyetest: nSelf ? _r2(sumSelf / nSelf) : 0,
            avg_cl_revenue_share: nClRev ? _r2(sumClRev / nClRev) : 0,
            avg_sales_per_emp: nSalesAvg ? _r2(sumSalesAvg / nSalesAvg) : 0,
            avg_sales_achievement: nSalesAch ? _r2(sumSalesAch / nSalesAch) : 0,
            total_sale: _r2(sumTotalSale),
            total_complaints: sumComplaints,
            total_redflags: sumRedFlags
          };
        }
      }
    } catch(ex) { areaResult.store_summary = {error: ex.toString()}; }

    // === LEARNING SHEET ===
    try {
      var lnSh = ss.getSheetByName(cfg.learnSheet);
      if (lnSh) {
        var lnData = lnSh.getDataRange().getValues();
        var lnHdrRow = -1;
        for (var r5 = 0; r5 < Math.min(5, lnData.length); r5++) {
          if (String(lnData[r5][0]).trim() === "Month") { lnHdrRow = r5; break; }
        }
        if (lnHdrRow >= 0) {
          var lnHdr = lnData[lnHdrRow];
          var cClasses = _colIdx(lnHdr, "Classes");
          var cHours = _colIdx(lnHdr, "Training Hours");
          var cParts = _colIdx(lnHdr, "Participants");
          var cSurveyAvg = _colIdx(lnHdr, "Survey Avg");
          var cSurveyVg = _colIdx(lnHdr, "Survey Very Good");
          var cObtSess = _colIdx(lnHdr, "OBT Sessions");
          var cObtPass = _colIdx(lnHdr, "OBT Pass");
          var cConnectUsers = _colIdx(lnHdr, "Connect Active Users");
          var cCerts = _colIdx(lnHdr, "New Grade");
          var cEvalGapCol = _colIdx(lnHdr, "Eval Gap");

          var tClasses = 0, tHours = 0, tParts = 0, tObtSess = 0, tCerts = 0, tConnectUsers = 0, tEvalGapCol = 0;
          var tSurvey = 0, nSurvey = 0, tSurveyVg = 0, nSurveyVg = 0, tObtPass = 0, nObtPass = 0;

          for (var r6 = lnHdrRow + 1; r6 < lnData.length; r6++) {
            var lrow = lnData[r6];
            var monthStr = String(lrow[0]).trim();
            if (!monthStr || monthStr === "" || monthStr.indexOf("TOTAL") >= 0) continue;

            if (cClasses >= 0) tClasses += _pNum(lrow[cClasses]);
            if (cHours >= 0) tHours += _pNum(lrow[cHours]);
            if (cParts >= 0) tParts += _pNum(lrow[cParts]);
            if (cObtSess >= 0) tObtSess += _pNum(lrow[cObtSess]);
            if (cCerts >= 0) tCerts += _pNum(lrow[cCerts]);
            if (cConnectUsers >= 0) tConnectUsers += _pNum(lrow[cConnectUsers]);
            if (cEvalGapCol >= 0) tEvalGapCol += _pNum(lrow[cEvalGapCol]);
            if (cSurveyAvg >= 0) { var svA = _pNum(lrow[cSurveyAvg]); if (svA > 0) { tSurvey += svA; nSurvey++; } }
            if (cSurveyVg >= 0) { var svV = _pNum(lrow[cSurveyVg]); if (svV > 0) { tSurveyVg += svV; nSurveyVg++; } }
            if (cObtPass >= 0) { var obp = _pNum(lrow[cObtPass]); if (obp > 0) { tObtPass += obp; nObtPass++; } }
          }

          areaResult.learning_summary = {
            total_classes: tClasses,
            total_hours: _r2(tHours),
            total_participants: tParts,
            avg_survey: nSurvey ? _r2(tSurvey / nSurvey) : 0,
            avg_survey_vg: nSurveyVg ? _r2(tSurveyVg / nSurveyVg) : 0,
            avg_obt_pass_pct: nObtPass ? _r2(tObtPass / nObtPass) : 0,
            total_obt_sessions: tObtSess,
            total_connect_users: tConnectUsers,
            total_certs: tCerts,
            eval_gap_from_learning: tEvalGapCol
          };
        }
      }
    } catch(ex) { areaResult.learning_summary = {error: ex.toString()}; }

    result.areas[areaCode] = areaResult;
  }

  return result;
}

// ============================================================
// ASSESSMENT — Grading Assessment Matrix
// Sheet: "Assessment" in Employee Master Data
// ============================================================
function getAssessmentData() {
  // --- inline helpers ---
  function _colIdx(hdr, kw) {
    for (var i = 0; i < hdr.length; i++) {
      var h = String(hdr[i]).replace(/\n/g, " ").trim();
      if (h === kw) return i;
    }
    for (var j = 0; j < hdr.length; j++) {
      var h2 = String(hdr[j]).replace(/\n/g, " ").trim();
      if (h2.indexOf(kw) >= 0) return j;
    }
    return -1;
  }
  // --- end helpers ---

  var ss;
  try { ss = SpreadsheetApp.openById(ASSESS_ID); }
  catch(e) { return {status:"error", message:"Cannot open Assessment sheet: " + e}; }

  var sheet = ss.getSheetByName("Assessment");
  if (!sheet) return {status:"error", message:"Sheet 'Assessment' not found"};

  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return {status:"success", employees:[], found_sheet:"Assessment"};

  // Find header row
  var hdrRow = -1;
  for (var r = 0; r < Math.min(5, data.length); r++) {
    for (var c = 0; c < data[r].length; c++) {
      if (String(data[r][c]).trim() === "EmpID") { hdrRow = r; break; }
    }
    if (hdrRow >= 0) break;
  }
  if (hdrRow < 0) return {status:"error", message:"Header row with 'EmpID' not found"};

  var hdr = data[hdrRow];

  var cEmpId = _colIdx(hdr, "EmpID");
  var cNickname = _colIdx(hdr, "Nickname");
  var cPosition = _colIdx(hdr, "Position");
  var cStatus = _colIdx(hdr, "Status");
  var cArea = _colIdx(hdr, "Store Area");
  var cStore = _colIdx(hdr, "Store");

  var COURSES = ["1st BCL","2nd BCL","3rd BCL","1st GBT","2nd GBT","1st SMT","2nd SMT","MCL [OP]","MCL [OD]","MTCL [OP]","MTCL [OD]"];
  var courseCols = {};
  for (var ci = 0; ci < COURSES.length; ci++) {
    courseCols[COURSES[ci]] = _colIdx(hdr, COURSES[ci]);
  }

  var c3rdGrade = _colIdx(hdr, "3rd Grade");
  var c2ndGrade = _colIdx(hdr, "2nd Grade");
  var c1stGrade = _colIdx(hdr, "1st Grade");

  var employees = [];

  for (var r2 = hdrRow + 1; r2 < data.length; r2++) {
    var row = data[r2];
    var empId = cEmpId >= 0 ? String(row[cEmpId]).trim() : "";
    if (!empId || empId === "" || empId === "0") continue;

    var status = cStatus >= 0 ? String(row[cStatus]).trim() : "";
    var nickname = cNickname >= 0 ? String(row[cNickname]).trim() : "";
    var position = cPosition >= 0 ? String(row[cPosition]).trim() : "";
    var area = cArea >= 0 ? String(row[cArea]).trim() : "";
    var store = cStore >= 0 ? String(row[cStore]).trim() : "";

    var courseStatus = {};
    for (var ck in courseCols) {
      var col = courseCols[ck];
      if (col >= 0) {
        var val = String(row[col]).trim().toUpperCase();
        courseStatus[ck] = (val === "P" || val === "PASS") ? "P" : "";
      } else {
        courseStatus[ck] = "";
      }
    }

    var grade = "";
    if (c1stGrade >= 0 && String(row[c1stGrade]).trim()) grade = "1st";
    else if (c2ndGrade >= 0 && String(row[c2ndGrade]).trim()) grade = "2nd";
    else if (c3rdGrade >= 0 && String(row[c3rdGrade]).trim()) grade = "3rd";

    employees.push({
      empId: empId,
      nickname: nickname,
      position: position,
      status: status,
      area: area,
      store: store,
      courses: courseStatus,
      grade: grade
    });
  }

  return {
    status: "success",
    found_sheet: "Assessment",
    total: employees.length,
    employees: employees
  };
}

// ============================================================
// EMPLOYEE MANAGEMENT (v10 ใหม่)
// ไฟล์เดียวกับ Assessment (ASSESS_ID = Employee Master ทั้งไฟล์):
//   Employee (หน้าร้าน), HQ (office), Resigned employee, Training, Assessment
// + OAR (OAR_ID) ทั้ง 2 tab: Registrations = ลงในคลาส, Registration (OBT) = OBT
// ============================================================
function getEmployeeManagementData() {
  // --- inline helpers ---
  function _colIdx(hdr, kw) {
    for (var i = 0; i < hdr.length; i++) {
      var h = String(hdr[i]).replace(/\n/g, " ").trim();
      if (h.indexOf(kw) >= 0) return i;
    }
    return -1;
  }
  function _monthKey(v) {
    if (!v) return "";
    var s = String(v);
    if (s.match(/^\d{4}-\d{2}/)) return s.substring(0, 7);
    try {
      var d = new Date(v);
      if (!isNaN(d.getTime())) return Utilities.formatDate(d, "Asia/Bangkok", "yyyy-MM");
    } catch(ex) {}
    return "";
  }
  // Employee และ HQ ใช้หัวคอลัมน์ชุดเดียวกัน (EmpID...Grade) — ใช้ helper ร่วม
  function _summarizeStaffSheet(sheet) {
    var data = sheet.getDataRange().getValues();
    if (data.length < 2) {
      return {total: 0, active: 0, resigned: 0, language_count: 0, grade_1st: 0, grade_2nd: 0, grade_3rd: 0, no_grade: 0};
    }
    var hdr = data[0];
    var cStatus = _colIdx(hdr, "Status");
    var cLang = _colIdx(hdr, "language");
    var cGrade = _colIdx(hdr, "Grade");

    var total = 0, active = 0, resigned = 0, langCount = 0, g1 = 0, g2 = 0, g3 = 0, noGrade = 0;
    for (var r = 1; r < data.length; r++) {
      var row = data[r];
      if (!row[0] || String(row[0]).trim() === "") continue;
      total++;

      var status = cStatus >= 0 ? String(row[cStatus]).trim() : "";
      if (status === "Resign") resigned++; else active++;

      if (cLang >= 0) {
        var lang = String(row[cLang]).trim();
        if (lang && lang !== "-" && lang.toLowerCase() !== "null") langCount++;
      }

      if (cGrade >= 0) {
        var gr = String(row[cGrade]).trim();
        if (gr === "1" || gr === "1st") g1++;
        else if (gr === "2" || gr === "2nd") g2++;
        else if (gr === "3" || gr === "3rd") g3++;
        else noGrade++;
      }
    }
    return {total: total, active: active, resigned: resigned, language_count: langCount, grade_1st: g1, grade_2nd: g2, grade_3rd: g3, no_grade: noGrade};
  }
  // --- end helpers ---

  var out = {
    status: "success",
    store_staff: {}, office_staff: {}, resigned_monthly: {},
    not_yet_trained: {}, not_yet_passed: 0,
    oar_monthly: {in_class: {}, obt: {}}
  };

  var ss;
  try { ss = SpreadsheetApp.openById(ASSESS_ID); }
  catch(e) { return {status:"error", message:"Cannot open Employee Master: " + e}; }

  // === Employee (หน้าร้าน) ===
  try {
    var empSh = ss.getSheetByName("Employee");
    out.store_staff = empSh ? _summarizeStaffSheet(empSh) : {error: "Sheet 'Employee' not found"};
  } catch(ex) { out.store_staff = {error: ex.toString()}; }

  // === HQ (office) ===
  try {
    var hqSh = ss.getSheetByName("HQ");
    out.office_staff = hqSh ? _summarizeStaffSheet(hqSh) : {error: "Sheet 'HQ' not found"};
  } catch(ex) { out.office_staff = {error: ex.toString()}; }

  // === Resigned employee — จำนวนลาออกต่อเดือน ===
  try {
    var resSh = ss.getSheetByName("Resigned employee");
    if (resSh) {
      var resData = resSh.getDataRange().getValues();
      if (resData.length >= 2) {
        var resHdr = resData[0];
        var cResignDate = _colIdx(resHdr, "Resign Date");
        if (cResignDate < 0) cResignDate = _colIdx(resHdr, "Last date");
        var monthly = {};
        for (var r = 1; r < resData.length; r++) {
          var row = resData[r];
          if (!row[0] || String(row[0]).trim() === "") continue;
          var mk = cResignDate >= 0 ? _monthKey(row[cResignDate]) : "";
          if (!mk) mk = "unknown";
          monthly[mk] = (monthly[mk] || 0) + 1;
        }
        out.resigned_monthly = monthly;
      }
    } else {
      out.resigned_monthly = {error: "Sheet 'Resigned employee' not found"};
    }
  } catch(ex) { out.resigned_monthly = {error: ex.toString()}; }

  // === Training — จำนวนคนยังไม่ได้เทรนต่อคอร์ส (matrix P/blank แบบเดียวกับ Assessment) ===
  try {
    var trainSh = ss.getSheetByName("Training");
    if (trainSh) {
      var trainData = trainSh.getDataRange().getValues();
      if (trainData.length >= 2) {
        var trainHdr = trainData[0];
        // Training tab ใช้รหัสคอร์สแบบเดียวกับ Survey/OAR (OTT/PE/BSC/... ) คนละชุดกับ
        // Assessment tab (1st BCL/GBT/SMT/MCL/MTCL — สำหรับสายเลนส์/คอนแทคเลนส์โดยเฉพาะ)
        var COURSES = ["OTT","PE","BSC","BOC","BVC","MSC","MOC","MVC","MTSC","MTOC","MTVC"];
        var courseCols = {};
        var anyFound = false;
        for (var ci = 0; ci < COURSES.length; ci++) {
          var idx = _colIdx(trainHdr, COURSES[ci]);
          courseCols[COURSES[ci]] = idx;
          if (idx >= 0) anyFound = true;
        }
        if (anyFound) {
          var totalRows = 0, notTrained = {};
          for (var ck in courseCols) notTrained[ck] = 0;
          for (var r2 = 1; r2 < trainData.length; r2++) {
            var trow = trainData[r2];
            if (!trow[0] || String(trow[0]).trim() === "") continue;
            totalRows++;
            for (var ck2 in courseCols) {
              var col = courseCols[ck2];
              if (col >= 0) {
                // Training tab เก็บวันที่เทรน ไม่ใช่ P/PASS แบบ Assessment — เซลล์มีค่า = เทรนแล้ว, เซลล์ว่าง/"-" = ยังไม่เทรน
                var val = String(trow[col]).trim();
                if (!val || val === "-" || val.toLowerCase() === "null") notTrained[ck2]++;
              }
            }
          }
          out.not_yet_trained = {total_staff: totalRows, per_course: notTrained};
        } else {
          // โครงสร้างจริงไม่ตรงที่คาดไว้ — ส่งหัวคอลัมน์ที่เจอจริงกลับไปด้วยเพื่อ debug ต่อได้ทันที
          out.not_yet_trained = {error: "Training sheet header ไม่ตรงกับ course columns ที่คาดไว้", headers_found: trainHdr};
        }
      }
    } else {
      out.not_yet_trained = {error: "Sheet 'Training' not found"};
    }
  } catch(ex) { out.not_yet_trained = {error: ex.toString()}; }

  // === Assessment — จำนวนคนสถานะ Pass (ยัง active) แต่ยังไม่มี grade ===
  try {
    var assessData = getAssessmentData();
    if (assessData.status === "success") {
      out.not_yet_passed = assessData.employees.filter(function(e) {
        return e.status === "Pass" && !e.grade;
      }).length;
    } else {
      out.not_yet_passed = {error: assessData.message};
    }
  } catch(ex) { out.not_yet_passed = {error: ex.toString()}; }

  // === OAR — ลงทะเบียนในคลาส vs OBT ต่อเดือน ===
  try {
    var oarSs = SpreadsheetApp.openById(OAR_ID);
    // ชื่อ tab OBT อาจสะกด/เว้นวรรคต่างจากที่คาด — ถ้าหาตรงชื่อไม่เจอ scan หา tab ที่มีคำว่า "obt" แทน
    function _findObtSheet(ss) {
      var sheets = ss.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        if (sheets[i].getName().toLowerCase().indexOf("obt") >= 0) return sheets[i];
      }
      return null;
    }
    var tabs = [{name: "Registrations", key: "in_class"}, {name: "Registration (OBT)", key: "obt"}];
    for (var ti = 0; ti < tabs.length; ti++) {
      var tabInfo = tabs[ti];
      var tSheet = oarSs.getSheetByName(tabInfo.name);
      if (!tSheet && tabInfo.key === "obt") tSheet = _findObtSheet(oarSs);
      if (!tSheet) {
        var oarSheetNames = oarSs.getSheets().map(function(s){ return s.getName(); });
        out.oar_monthly[tabInfo.key] = {error: "Sheet '" + tabInfo.name + "' not found. Available sheets: " + oarSheetNames.join(", ")};
        continue;
      }
      var tData = tSheet.getDataRange().getValues();
      if (tData.length < 2) { out.oar_monthly[tabInfo.key] = {}; continue; }
      var tHdr = tData[0];
      var cDate = _colIdx(tHdr, "Training Date");
      if (cDate < 0) cDate = _colIdx(tHdr, "Timestamp");
      var cFullName = _colIdx(tHdr, "Full Name");
      var monthly2 = {};
      for (var r3 = 1; r3 < tData.length; r3++) {
        var trow2 = tData[r3];
        if (cFullName >= 0 && String(trow2[cFullName]).trim() === "") continue;
        var mk2 = cDate >= 0 ? _monthKey(trow2[cDate]) : "";
        if (!mk2) mk2 = "unknown";
        monthly2[mk2] = (monthly2[mk2] || 0) + 1;
      }
      out.oar_monthly[tabInfo.key] = monthly2;
    }
  } catch(ex) { out.oar_monthly = {error: ex.toString()}; }

  return out;
}

// ============================================================
// ACADEMY (v10 ใหม่) — สรุปภาพรวม L&D จากทุก action ไว้ที่เดียว
// ฉบับดราฟ — ปรับเพิ่ม/ลดตัวเลขได้ทีหลังตามที่คุยกัน
// ============================================================
function getAcademyData() {
  try {
    var survey = getSurveyData("");
    var assessment = getAssessmentData();
    var employee = getEmployeeManagementData();
    var cost = getCostData("");
    var asset = getAssetData();

    var activeAssess = (assessment.status === "success")
      ? assessment.employees.filter(function(e){ return e.status === "Pass"; })
      : [];
    var gradedCount = activeAssess.filter(function(e){ return !!e.grade; }).length;

    return {
      status: "success",
      generated_at: new Date().toISOString(),
      headcount: {
        store: (employee.store_staff && employee.store_staff.total) || 0,
        office: (employee.office_staff && employee.office_staff.total) || 0
      },
      assessment: {
        active_total: activeAssess.length,
        graded: gradedCount,
        not_yet_passed: employee.not_yet_passed
      },
      training: {
        total_responses: survey.total_responses || 0,
        overall_avg: survey.overall_avg || 0,
        trainer_count: survey.trainers ? survey.trainers.length : 0
      },
      cost: {
        budget: cost.budget || 0,
        actual: cost.actual || 0,
        balance: cost.balance || 0
      },
      asset: {
        total_laptops: asset.total_laptops || 0,
        total_ipads: asset.total_ipads || 0,
        issues: asset.issues || 0
      }
    };
  } catch(ex) {
    return {status: "error", message: ex.toString()};
  }
}

// ============================================================
// OD-CONNECT (v10 ใหม่) — สรุปการใช้งาน od-connect.com จาก Google Analytics 4
// เพื่อประมวลผล digital transformation ขององค์กร
//
// Auth แบบง่าย: ใช้ตัวตน Google ของคนที่ deploy สคริปต์นี้เอง (ScriptApp.getOAuthToken())
// ไม่ต้องสร้าง service account/key JSON แยก — เงื่อนไขคือบัญชี Google ที่ deploy ต้อง
// มีสิทธิ์ดู GA4 property นี้อยู่แล้ว (ถ้าเปิดลิงก์ analytics.google.com/.../a268231845p539554359
// แล้วเห็นข้อมูลปกติ = มีสิทธิ์แล้ว ไม่ต้องแชร์เพิ่ม)
//
// วิธี setup (ทำครั้งเดียว):
//   1. เช็คว่า "Google Analytics Data API" เปิดใช้อยู่ใน GCP project ของสคริปต์นี้ไหม:
//      Apps Script editor > Project Settings (รูปเฟือง) > ดู "Google Cloud Platform (GCP) Project"
//      จะได้เลข project number -> ไปที่ console.cloud.google.com เลือก project นั้น (หรือค้นด้วย
//      เลข project number) -> APIs & Services > Enable APIs -> ค้นหา "Google Analytics Data API" -> Enable
//   2. Apps Script editor > Project Settings > ติ๊ก "Show appsscript.json manifest file in editor"
//   3. เปิดไฟล์ appsscript.json ที่โผล่มาในรายการไฟล์ทางซ้าย -> เพิ่ม (ไม่ใช่แทนทั้งไฟล์) key
//      "oauthScopes" ที่มี "https://www.googleapis.com/auth/analytics.readonly" รวมอยู่ด้วย
//      พร้อมกับ scope เดิมที่สคริปต์นี้ใช้อยู่แล้ว (Sheets อ่าน + external request) — ถ้าไม่แน่ใจ
//      โครงเดิมมีอะไรอยู่บ้าง ส่งเนื้อไฟล์ appsscript.json ปัจจุบันมาให้ดูก่อนได้ จะช่วย merge ให้ถูก
//   4. Save แล้วรันฟังก์ชันไหนก็ได้ 1 ครั้งในตัว editor (เช่น doGet) เพื่อให้ Apps Script ขึ้น
//      หน้าขอสิทธิ์ใหม่ (Authorize) -> กด Allow -> เสร็จแล้ว ไม่ต้องมี Script Property ใดๆเลย
// ============================================================
function _ga4RunReport(body) {
  var token = ScriptApp.getOAuthToken();
  var url = "https://analyticsdata.googleapis.com/v1beta/properties/" + GA4_PROPERTY_ID + ":runReport";
  var resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {Authorization: "Bearer " + token},
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  });
  var json = JSON.parse(resp.getContentText());
  if (json.error) throw new Error("GA4 API error: " + JSON.stringify(json.error));
  return json;
}

function getOdConnectData(days) {
  days = days || 28;
  try {
    var dateRange = [{startDate: days + "daysAgo", endDate: "today"}];

    // --- Overview ---
    var overviewResp = _ga4RunReport({
      dateRanges: dateRange,
      metrics: [
        {name: "sessions"}, {name: "activeUsers"}, {name: "newUsers"},
        {name: "screenPageViews"}, {name: "bounceRate"}, {name: "averageSessionDuration"}
      ]
    });
    var ov = (overviewResp.rows && overviewResp.rows[0] && overviewResp.rows[0].metricValues) || [];
    var overview = {
      sessions: ov[0] ? Number(ov[0].value) : 0,
      active_users: ov[1] ? Number(ov[1].value) : 0,
      new_users: ov[2] ? Number(ov[2].value) : 0,
      page_views: ov[3] ? Number(ov[3].value) : 0,
      bounce_rate_pct: ov[4] ? Math.round(Number(ov[4].value) * 10000) / 100 : 0,
      avg_session_sec: ov[5] ? Math.round(Number(ov[5].value)) : 0
    };

    // --- Daily trend (สำหรับกราฟเส้น) ---
    var trendResp = _ga4RunReport({
      dateRanges: dateRange,
      dimensions: [{name: "date"}],
      metrics: [{name: "sessions"}, {name: "activeUsers"}],
      orderBys: [{dimension: {dimensionName: "date"}}]
    });
    var trend = (trendResp.rows || []).map(function(row) {
      return {
        date: row.dimensionValues[0].value,
        sessions: Number(row.metricValues[0].value),
        users: Number(row.metricValues[1].value)
      };
    });

    // --- Top pages ---
    var pagesResp = _ga4RunReport({
      dateRanges: dateRange,
      dimensions: [{name: "pagePath"}],
      metrics: [{name: "screenPageViews"}, {name: "activeUsers"}],
      orderBys: [{metric: {metricName: "screenPageViews"}, desc: true}],
      limit: 10
    });
    var topPages = (pagesResp.rows || []).map(function(row) {
      return {path: row.dimensionValues[0].value, page_views: Number(row.metricValues[0].value), users: Number(row.metricValues[1].value)};
    });

    // --- Traffic sources ---
    var sourceResp = _ga4RunReport({
      dateRanges: dateRange,
      dimensions: [{name: "sessionDefaultChannelGroup"}],
      metrics: [{name: "sessions"}],
      orderBys: [{metric: {metricName: "sessions"}, desc: true}],
      limit: 8
    });
    var trafficSources = (sourceResp.rows || []).map(function(row) {
      return {channel: row.dimensionValues[0].value, sessions: Number(row.metricValues[0].value)};
    });

    // --- Devices ---
    var deviceResp = _ga4RunReport({
      dateRanges: dateRange,
      dimensions: [{name: "deviceCategory"}],
      metrics: [{name: "sessions"}],
      orderBys: [{metric: {metricName: "sessions"}, desc: true}]
    });
    var devices = (deviceResp.rows || []).map(function(row) {
      return {device: row.dimensionValues[0].value, sessions: Number(row.metricValues[0].value)};
    });

    return {
      status: "success",
      property_id: GA4_PROPERTY_ID,
      period_days: days,
      overview: overview,
      trend: trend,
      top_pages: topPages,
      traffic_sources: trafficSources,
      devices: devices
    };
  } catch(ex) {
    return {status: "error", message: ex.toString()};
  }
}
