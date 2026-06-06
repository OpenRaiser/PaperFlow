(function () {
  const uiState = {
    reports: [],
    currentReport: null,
    recentReportIds: [],
  };

  const byId = (id) => document.getElementById(id);

  function ensureReportsDom() {
    const nav = document.querySelector('[data-view="reports"]');
    if (nav) {
      nav.textContent = "报告阅读";
      nav.onclick = () => {
        showReportsView().catch(console.error);
      };
    } else {
      const readingNav = document.querySelector('[data-view="reading"]');
      if (readingNav?.parentElement) {
        const button = document.createElement("button");
        button.className = "nav-item";
        button.dataset.view = "reports";
        button.textContent = "报告阅读";
        button.onclick = () => {
          showReportsView().catch(console.error);
        };
        readingNav.insertAdjacentElement("afterend", button);
      }
    }

    if (byId("reports")) return;

    const wikiSection = byId("wiki");
    if (!wikiSection) return;

    const section = document.createElement("section");
    section.id = "reports";
    section.className = "view";
    section.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3>报告阅读</h3>
            <p>在 GUI 中浏览和阅读本地 Markdown 精读报告。</p>
          </div>
          <div class="actions">
            <select id="reportDays" title="时间范围">
              <option value="7">最近 7 天</option>
              <option value="30" selected>最近 30 天</option>
              <option value="90">最近 90 天</option>
              <option value="365">全部</option>
            </select>
            <button id="reportTodayBtn" type="button">今天</button>
            <button id="refreshReportsBtn" type="button">刷新</button>
          </div>
        </div>

        <div class="reports-toolbar">
          <input id="reportQuery" placeholder="搜索标题、arXiv ID 或路径">
          <input id="reportDate" type="date" aria-label="精确日期筛选">
          <label class="checkline subtle-check">
            <input id="reportsCurrentOnly" type="checkbox" checked>
            仅看当前用户
          </label>
        </div>

        <div id="reportSources" class="meta-line">报告目录尚未加载。</div>

        <div class="reports-layout">
          <div id="reportsList" class="result-list empty">尚未加载报告列表。</div>

          <div class="report-viewer">
            <div class="report-viewer-head">
              <div>
                <h3 id="reportViewerTitle">选择一篇报告</h3>
                <p id="reportViewerMeta" class="meta-line">从左侧列表打开一篇报告后，这里显示正文内容。</p>
              </div>
              <div class="actions">
                <button id="openReportAbsBtn" type="button" disabled>原文</button>
                <button id="openReportPdfBtn" type="button" disabled>PDF</button>
                <button id="openReportDocBtn" type="button" disabled>飞书</button>
                <button id="copyReportPathBtn" type="button" disabled>复制路径</button>
              </div>
            </div>

            <div class="report-viewer-layout">
              <article id="reportViewerBody" class="markdown-body empty">尚未选择报告。</article>
            </div>
          </div>
        </div>
      </div>
    `;
    wikiSection.insertAdjacentElement("beforebegin", section);
  }

  function setView(name) {
    const targetView = byId(name);
    const targetNav = document.querySelector(`[data-view="${name}"]`);
    if (!targetView || !targetNav) return;
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    targetView.classList.add("active");
    targetNav.classList.add("active");
    if (byId("pageTitle")) {
      byId("pageTitle").textContent = targetNav.textContent;
    }
  }

  async function showReportsView(options = {}) {
    ensureReportsDom();
    setView("reports");
    await refreshReports({ keepSelection: true, ...options });
  }

  function renderInlineMarkdown(text) {
    let html = window.escapeHtml ? window.escapeHtml(text || "") : String(text || "");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noreferrer">$2</a>');
    return html;
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let paragraph = [];
    let listItems = [];
    let listType = "";
    let quoteLines = [];
    let inCode = false;
    let codeLines = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      out.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    };
    const flushList = () => {
      if (!listItems.length) return;
      out.push(`<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`);
      listItems = [];
      listType = "";
    };
    const flushQuote = () => {
      if (!quoteLines.length) return;
      out.push(`<blockquote>${quoteLines.map((item) => `<p>${renderInlineMarkdown(item)}</p>`).join("")}</blockquote>`);
      quoteLines = [];
    };
    const flushCode = () => {
      if (!inCode) return;
      out.push(`<pre><code>${window.escapeHtml ? window.escapeHtml(codeLines.join("\n")) : codeLines.join("\n")}</code></pre>`);
      inCode = false;
      codeLines = [];
    };

    for (const rawLine of lines) {
      const line = rawLine.replace(/\t/g, "  ");
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        flushParagraph();
        flushList();
        flushQuote();
        if (inCode) flushCode();
        else {
          inCode = true;
          codeLines = [];
        }
        continue;
      }
      if (inCode) {
        codeLines.push(line);
        continue;
      }
      if (!trimmed) {
        flushParagraph();
        flushList();
        flushQuote();
        continue;
      }
      const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        flushParagraph();
        flushList();
        flushQuote();
        const level = heading[1].length;
        out.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }
      const quote = trimmed.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        quoteLines.push(quote[1]);
        continue;
      }
      const unordered = trimmed.match(/^[-*]\s+(.*)$/);
      if (unordered) {
        flushParagraph();
        flushQuote();
        if (listType && listType !== "ul") flushList();
        listType = "ul";
        listItems.push(unordered[1]);
        continue;
      }
      const ordered = trimmed.match(/^\d+\.\s+(.*)$/);
      if (ordered) {
        flushParagraph();
        flushQuote();
        if (listType && listType !== "ol") flushList();
        listType = "ol";
        listItems.push(ordered[1]);
        continue;
      }
      flushList();
      flushQuote();
      paragraph.push(trimmed);
    }

    flushParagraph();
    flushList();
    flushQuote();
    flushCode();
    return out.join("");
  }

  function renderMeta(report) {
    const target = byId("reportMetadata");
    if (!target) return;
    const metadata = report.metadata || {};
    const rows = [
      ["user_id", report.user_id || metadata.user_id || ""],
      ["paper_id", report.paper_id || metadata.paper_id || ""],
      ["arxiv_id", report.arxiv_id || metadata.arxiv_id || ""],
      ["saved_at", report.saved_at || metadata.saved_at || ""],
      ["report_version", report.report_version || metadata.report_version || ""],
      ["generation_provider", report.generation_provider || metadata.generation_provider || ""],
      ["generation_model", report.generation_model || metadata.generation_model || ""],
      ["doc_token", report.doc_token || metadata.doc_token || ""],
      ["report_path", report.report_path || ""],
    ].filter(([, value]) => String(value || "").trim());

    if (!rows.length) {
      target.className = "settings-list empty";
      target.textContent = "暂无元数据。";
      return;
    }
    target.className = "report-meta-grid";
    target.innerHTML = rows.map(([label, value]) => `
      <div class="report-meta-item">
        <strong>${window.escapeHtml ? window.escapeHtml(label) : label}</strong>
        <code>${window.escapeHtml ? window.escapeHtml(value) : value}</code>
      </div>
    `).join("");
  }

  function renderEmpty(message) {
    uiState.currentReport = null;
    byId("reportViewerTitle").textContent = "选择一篇报告";
    byId("reportViewerMeta").textContent = "从左侧列表打开一篇报告后，这里显示正文内容。";
    byId("reportViewerBody").className = "markdown-body empty";
    byId("reportViewerBody").textContent = message;
    if (byId("reportMetadata")) {
      byId("reportMetadata").className = "settings-list empty";
      byId("reportMetadata").textContent = "暂无元数据。";
    }
    ["openReportAbsBtn", "openReportPdfBtn", "openReportDocBtn", "copyReportPathBtn"].forEach((id) => {
      const button = byId(id);
      button.disabled = true;
      delete button.dataset.href;
      delete button.dataset.path;
    });
  }

  function renderViewer(report) {
    uiState.currentReport = report;
    byId("reportViewerTitle").textContent = report.title || "精读报告";
    byId("reportViewerMeta").textContent = [report.user_id, report.saved_at || report.updated_at, report.report_path]
      .filter(Boolean)
      .join(" | ");
    byId("reportViewerBody").className = "markdown-body";
    byId("reportViewerBody").innerHTML = renderMarkdown(report.markdown || "");
    renderMeta(report);

    const linkMap = {
      openReportAbsBtn: report.abs_url || "",
      openReportPdfBtn: report.pdf_url || "",
      openReportDocBtn: report.doc_url || "",
    };
    Object.entries(linkMap).forEach(([id, href]) => {
      const button = byId(id);
      button.disabled = !href;
      if (href) button.dataset.href = href;
      else delete button.dataset.href;
    });
    const copyButton = byId("copyReportPathBtn");
    copyButton.disabled = !report.report_path;
    if (report.report_path) copyButton.dataset.path = report.report_path;
    else delete copyButton.dataset.path;
  }

  function renderList(reports, activeId = "") {
    const target = byId("reportsList");
    if (!reports.length) {
      target.className = "result-list empty";
      target.textContent = "没有匹配的精读报告。";
      return;
    }
    const recentSet = new Set(uiState.recentReportIds || []);
    const ordered = [
      ...reports.filter((item) => recentSet.has(item.report_id)),
      ...reports.filter((item) => !recentSet.has(item.report_id)),
    ];
    target.className = "reports-list";
    target.innerHTML = ordered.map((report) => `
      <button type="button" class="report-row ${report.report_id === activeId ? "active" : ""} ${recentSet.has(report.report_id) ? "recent" : ""}" data-report-id="${window.escapeHtml ? window.escapeHtml(report.report_id) : report.report_id}">
        <h4>${window.escapeHtml ? window.escapeHtml(report.title || "精读报告") : (report.title || "精读报告")}${recentSet.has(report.report_id) ? ' <span class="report-badge">本次生成</span>' : ''}</h4>
        <p>${window.escapeHtml ? window.escapeHtml(report.user_id || "未标记用户") : (report.user_id || "未标记用户")}${report.arxiv_id ? ` | ${window.escapeHtml ? window.escapeHtml(report.arxiv_id) : report.arxiv_id}` : ""}</p>
        <p>${window.escapeHtml ? window.escapeHtml(report.saved_at || report.updated_at || "") : (report.saved_at || report.updated_at || "")}</p>
        <p>${window.escapeHtml ? window.escapeHtml(report.snippet || report.report_path || "") : (report.snippet || report.report_path || "")}</p>
      </button>
    `).join("");
  }

  async function loadReportContent(reportId, silent = false) {
    if (!reportId) throw new Error("report_id is required");
    const data = await api(`/api/reports/content?report_id=${encodeURIComponent(reportId)}`);
    const report = data.report || null;
    renderList(uiState.reports, reportId);
    if (report) renderViewer(report);
    else renderEmpty("没有找到这篇报告。");
    if (!silent) setStatus("报告已打开");
  }

  async function refreshReports(options = {}) {
    ensureReportsDom();
    const userId = activeUser();
    if (!userId) return;
    const scopedUser = byId("reportsCurrentOnly").checked ? userId : "";
    const q = byId("reportQuery").value.trim();
    const days = Number(byId("reportDays").value || 30);
    const exactDate = byId("reportDate").value || "";
    const data = await api(`/api/reports?user_id=${encodeURIComponent(scopedUser)}&q=${encodeURIComponent(q)}&days=${encodeURIComponent(days)}&date=${encodeURIComponent(exactDate)}&limit=120`);
    uiState.reports = data.reports || [];
    const sourceDirs = data.source_dirs || [];
    const filters = [];
    if (exactDate) filters.push(`date=${exactDate}`);
    if (scopedUser) filters.push(`user=${scopedUser}`);
    byId("reportSources").textContent = sourceDirs.length
      ? `报告目录: ${sourceDirs.join(" | ")} | 数量=${data.count || 0}${filters.length ? ` | ${filters.join(" | ")}` : ""}`
      : `数量=${data.count || 0}${filters.length ? ` | ${filters.join(" | ")}` : ""}`;
    const preferredId = options.keepSelection && uiState.currentReport ? uiState.currentReport.report_id : "";
    const recentPreferred = uiState.reports.find((item) => (uiState.recentReportIds || []).includes(item.report_id));
    const selected = uiState.reports.find((item) => item.report_id === preferredId) || recentPreferred || uiState.reports[0] || null;
    renderList(uiState.reports, selected?.report_id || "");
    if (selected) await loadReportContent(selected.report_id, true);
    else renderEmpty("没有匹配当前筛选条件的报告。");
  }

  async function jumpToReport(reportId) {
    ensureReportsDom();
    setView("reports");
    await refreshReports({ keepSelection: false });
    await loadReportContent(reportId);
  }

  function overrideGenerationRenderers() {
    window.renderReports = function renderReportsOverride(reports) {
      const docs = reports.created_docs || [];
      uiState.recentReportIds = docs.map((doc) => doc.report_id).filter(Boolean);
      byId("reportResults").classList.remove("hidden");
      if (!docs.length) {
        byId("reportList").className = "empty";
        byId("reportList").textContent = "本次没有生成报告。";
        return;
      }
      byId("reportList").className = "";
      byId("reportList").innerHTML = docs.map((doc) => {
        const reportPath = doc.report_path ? `<p>Markdown：<code>${window.escapeHtml(doc.report_path)}</code></p>` : "";
        const pdfPath = doc.pdf_path ? `<p>PDF：<code>${window.escapeHtml(doc.pdf_path)}</code></p>` : "";
        const url = doc.url ? `<p><a href="${doc.url}" target="_blank" rel="noreferrer">打开飞书文档</a></p>` : "";
        const openAction = doc.report_id ? `<div class="actions"><button type="button" data-open-report="${window.escapeHtml(doc.report_id)}">在报告阅读中打开</button></div>` : "";
        return `<div class="report-item"><h4>${window.escapeHtml(doc.title || doc.paper?.title || "精读报告")}</h4>${reportPath}${pdfPath}${url}${openAction}</div>`;
      }).join("");
    };

    window.renderReportList = function renderReportListOverride(targetId, reports) {
      const docs = reports.created_docs || [];
      uiState.recentReportIds = docs.map((doc) => doc.report_id).filter(Boolean);
      const target = byId(targetId);
      if (!docs.length) {
        target.className = "empty";
        target.textContent = "本次没有生成报告。";
        return;
      }
      target.className = "";
      target.innerHTML = docs.map((doc) => {
        const reportPath = doc.report_path ? `<p>Markdown：<code>${window.escapeHtml(doc.report_path)}</code></p>` : "";
        const pdfPath = doc.pdf_path ? `<p>PDF：<code>${window.escapeHtml(doc.pdf_path)}</code></p>` : "";
        const url = doc.url ? `<p><a href="${doc.url}" target="_blank" rel="noreferrer">打开飞书文档</a></p>` : "";
        const openAction = doc.report_id ? `<div class="actions"><button type="button" data-open-report="${window.escapeHtml(doc.report_id)}">在报告阅读中打开</button></div>` : "";
        return `<div class="report-item"><h4>${window.escapeHtml(doc.title || doc.paper?.title || "精读报告")}</h4>${reportPath}${pdfPath}${url}${openAction}</div>`;
      }).join("");
    };
  }

  function bindReportsEvents() {
    byId("userSelect")?.addEventListener("change", () => {
      if (document.querySelector('[data-view="reports"]')?.classList.contains("active")) {
        refreshReports({ keepSelection: false }).catch(console.error);
      }
    });
    byId("refreshReportsBtn")?.addEventListener("click", () => runAction(() => refreshReports({ keepSelection: true })));
    byId("reportDays")?.addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false })));
    byId("reportDate")?.addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false })));
    byId("reportsCurrentOnly")?.addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false })));
    byId("reportQuery")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runAction(() => refreshReports({ keepSelection: false }));
    });
    byId("reportTodayBtn")?.addEventListener("click", () => {
      byId("reportDate").value = new Date().toISOString().slice(0, 10);
      runAction(() => refreshReports({ keepSelection: false }));
    });
    byId("reportsList")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-report-id]");
      if (button) runAction(() => loadReportContent(button.dataset.reportId));
    });
    ["reportList", "directReportList"].forEach((id) => {
      byId(id)?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-open-report]");
        if (button) runAction(() => jumpToReport(button.dataset.openReport));
      });
    });
    ["openReportAbsBtn", "openReportPdfBtn", "openReportDocBtn"].forEach((id) => {
      byId(id)?.addEventListener("click", () => {
        const href = byId(id).dataset.href;
        if (href) window.open(href, "_blank", "noopener,noreferrer");
      });
    });
    byId("copyReportPathBtn")?.addEventListener("click", async () => {
      const path = byId("copyReportPathBtn").dataset.path || "";
      if (!path) return;
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(path);
      else window.prompt("复制报告路径", path);
      setStatus("报告路径已复制");
    });
  }

  function init() {
    ensureReportsDom();
    overrideGenerationRenderers();
    bindReportsEvents();
  }

  window.refreshReports = refreshReports;
  window.loadReportContent = (reportId) => loadReportContent(reportId, false);
  window.jumpToReport = jumpToReport;
  window.showReportsView = showReportsView;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
