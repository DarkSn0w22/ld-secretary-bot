// ============================================================
// L&D Dashboard — GAS API v9 (v8 + Cost tab-name fix)
// ทั้งไฟล์นี้เป็นสำเนาไว้เทียบ/track การเปลี่ยนแปลง — ต้อง copy วางทับ
// ใน Google Apps Script editor แล้ว Deploy ใหม่เองด้วยนะครับ (ยังไม่มี clasp เชื่อมตรง)
//
// v9 changes:
//   - getCostData(): ชื่อ tab จริงคือ "L&D Financial" ไม่ใช่ "Cost" (สาเหตุที่
//     action=cost error "Cost sheet not found" อยู่ก่อนหน้านี้) — แก้ _findSheet
//     ให้หา "L&D Financial" เป็นหลัก, เหลือ "Cost" ไว้เป็น fallback เผื่อเปลี่ยนชื่อกลับ,
//     และถ้าหาไม่เจอเลยจะ list ชื่อ sheet ทั้งหมดกลับไปด้วยเพื่อ debug ง่ายขึ้นในอนาคต
// ============================================================
var SURVEY_ID    = "1RlnQEXOJ3EPwqnuDLMk3rjBvinJbW1wKFcRyMfdlEVs";
var DASHBOARD_ID = "1QKjyFlmJrgmiYHagn7olhpr41ucQJQc8ck3zae8obJI";
var OAR_ID       = "1Ux83yvg3sdANd8_OB104Np9jartOfEF9_xhoX5JslSU";
var AREA_ID      = "1IQkFbrj8jOni9XgIn3CIWvGZgeJ2FMGTveBjy3sodWA";
var ASSESS_ID    = "1FLIugt_XASi_vsP7FHdL2UVthQQDsdZpH6St3zVofMU";

var RATING_MAP = {"Very good":4,"Good":3,"Quite Good":2,"Moderate":1,"Needs Improvement":0};

function doGet(e) {
  var p = (e && e.parameter) || {};
  var cb = p.callback || "";
  var year = p.year || "";
  var out;
  try {
    var act = p.action || "all";
    if (act === "all") {
      out = {status:"success", timestamp:new Date().toISOString(), year:year, survey:getSurveyData(year), cost:getCostData(year), asset:getAssetData(), oar:getOarData(year), area:getAreaData(), assessment:getAssessmentData()};
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
        var tn = String(row[trC]).trim();
        if (tn) {
          if (!trainerStats[tn]) trainerStats[tn] = {ts: 0, c: 0, cs: {}};
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

  var trR = [];
  for (var k in trainerStats) {
    var t = trainerStats[k];
    trR.push({name: k, avg: t.c ? _r2(t.ts / t.c) : 0, count: t.c, courses: t.cs});
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
// AREA — Area Performance Data
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
    "MS": {name: "Megastore", empSheet: "MS-Employee", storeSheet: "MS-Store", learnSheet: "MS-Learning"},
    "MT": {name: "Metropolitan", empSheet: "MT-Employee", storeSheet: "MT-Store", learnSheet: "MT-Learning"},
    "NC": {name: "North+Central", empSheet: "NC-Employee", storeSheet: "NC-Store", learnSheet: "NC-Learning"},
    "WN": {name: "West+NE", empSheet: "WN-Employee", storeSheet: "WN-Store", learnSheet: "WN-Learning"},
    "SE": {name: "South+Eastern", empSheet: "SE-Employee", storeSheet: "SE-Store", learnSheet: "SE-Learning"}
  };

  var result = {status: "success", areas: {}};

  for (var areaCode in AREA_MAP) {
    var cfg = AREA_MAP[areaCode];
    var areaResult = {name: cfg.name, employee_summary: {}, store_summary: {}, learning_summary: {}};

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

          var total = 0, probation = 0, confirmed = 0;
          var obtPass = 0, obtProg = 0, obtNot = 0;
          var g1 = 0, g2 = 0, g3 = 0, evalGap = 0;

          for (var r2 = empHdrRow + 1; r2 < empData.length; r2++) {
            var row = empData[r2];
            if (!row[0] || String(row[0]).trim() === "") continue;
            total++;

            if (cProb >= 0) {
              var ps = String(row[cProb]).trim();
              if (ps === "Confirmed") confirmed++;
              else if (ps.indexOf("Probation") >= 0 || ps === "Probation") probation++;
              else probation++;
            }

            if (cObt >= 0) {
              var os = String(row[cObt]).trim();
              if (os === "Pass") obtPass++;
              else if (os === "In Progress" || os.indexOf("Progress") >= 0) obtProg++;
              else if (os === "Not Started" || os === "" || os === "NaN") obtNot++;
              else obtNot++;
            }

            if (cGrade >= 0) {
              var gr = String(row[cGrade]).trim();
              if (gr === "1st") g1++;
              else if (gr === "2nd") g2++;
              else if (gr === "3rd") g3++;
            }
          }
          evalGap = total - (g1 + g2 + g3);
          if (evalGap < 0) evalGap = 0;

          areaResult.employee_summary = {
            total: total, probation: probation, confirmed: confirmed,
            obt_pass: obtPass, obt_in_progress: obtProg, obt_not_started: obtNot,
            grade_1st: g1, grade_2nd: g2, grade_3rd: g3, eval_gap: evalGap
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
          var cSalesAvg = _colIdx(stHdr, "Sales Avg");
          var cTotalSale = _colIdx(stHdr, "Total Sale");
          var cComplaint = _colIdx(stHdr, "Complaint");
          var cRedFlag = _colIdx(stHdr, "Red Flag");

          var sumTopup = 0, sumNps = 0, sumAcc = 0, sumSelf = 0;
          var sumSalesAvg = 0, sumTotalSale = 0, sumComplaints = 0, sumRedFlags = 0;
          var nTopup = 0, nNps = 0, nAcc = 0, nSelf = 0, nSalesAvg = 0, stRows = 0;

          for (var r4 = stHdrRow + 1; r4 < stData.length; r4++) {
            var srow = stData[r4];
            if (!srow[0] || String(srow[0]).trim() === "") continue;
            stRows++;

            if (cTopup >= 0) { var vt = _pNum(srow[cTopup]); if (vt > 0) { sumTopup += vt; nTopup++; } }
            if (cNps >= 0) { var vn = _pNum(srow[cNps]); if (vn > 0) { sumNps += vn; nNps++; } }
            if (cAcc >= 0) { var va = _pNum(srow[cAcc]); if (va > 0) { sumAcc += va; nAcc++; } }
            if (cSelfEye >= 0) { var vs = _pNum(srow[cSelfEye]); if (vs > 0) { sumSelf += vs; nSelf++; } }
            if (cSalesAvg >= 0) { var vsa = _pNum(srow[cSalesAvg]); if (vsa > 0) { sumSalesAvg += vsa; nSalesAvg++; } }
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
            avg_sales_per_emp: nSalesAvg ? _r2(sumSalesAvg / nSalesAvg) : 0,
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
          var cCerts = _colIdx(lnHdr, "New Grade");

          var tClasses = 0, tHours = 0, tParts = 0, tObtSess = 0, tCerts = 0;
          var tSurvey = 0, nSurvey = 0, tSurveyVg = 0, nSurveyVg = 0;

          for (var r6 = lnHdrRow + 1; r6 < lnData.length; r6++) {
            var lrow = lnData[r6];
            var monthStr = String(lrow[0]).trim();
            if (!monthStr || monthStr === "" || monthStr.indexOf("TOTAL") >= 0) continue;

            if (cClasses >= 0) tClasses += _pNum(lrow[cClasses]);
            if (cHours >= 0) tHours += _pNum(lrow[cHours]);
            if (cParts >= 0) tParts += _pNum(lrow[cParts]);
            if (cObtSess >= 0) tObtSess += _pNum(lrow[cObtSess]);
            if (cCerts >= 0) tCerts += _pNum(lrow[cCerts]);
            if (cSurveyAvg >= 0) { var svA = _pNum(lrow[cSurveyAvg]); if (svA > 0) { tSurvey += svA; nSurvey++; } }
            if (cSurveyVg >= 0) { var svV = _pNum(lrow[cSurveyVg]); if (svV > 0) { tSurveyVg += svV; nSurveyVg++; } }
          }

          areaResult.learning_summary = {
            total_classes: tClasses,
            total_hours: _r2(tHours),
            total_participants: tParts,
            avg_survey: nSurvey ? _r2(tSurvey / nSurvey) : 0,
            avg_survey_vg: nSurveyVg ? _r2(tSurveyVg / nSurveyVg) : 0,
            total_obt_sessions: tObtSess,
            total_certs: tCerts
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
