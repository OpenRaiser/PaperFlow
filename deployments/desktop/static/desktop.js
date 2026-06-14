(function () {
  "use strict";

  const DEMO_MODE = new URLSearchParams(window.location.search).get("demo") === "1";
  const state = {
    users: [],
    currentUser: "user_demo",
    push: null,
    selected: new Set(),
    skipped: new Set(),
    later: new Set(),
    paperReports: new Map(),
    paperReading: new Set(),
    feedbackTimer: null,
    sourceOptionsLoaded: false,
    sourceOptions: null,
    reports: [],
    currentReport: null,
    wikiNodes: [],
    wikiGraph: null,
    wikiMap: null,
    currentWikiNodeId: "",
    currentWikiEditNodeId: "",
    wikiView: "graph",
    currentProfile: null,
    profileLoadToken: 0,
    chatMentions: [],
    mentionSearchTimer: null,
    mentionSearchToken: 0,
    dailyTaskId: "",
    dailyTaskUserId: "",
    dailyPollToken: 0,
    dailyPolling: false
  };

  const demoPapers = [
    {
      number: 1,
      score: 92,
      title: "Efficient Test-Time Scaling for Reasoning Agents",
      authors: "A. Chen, M. Gupta, Y. Li · Stanford University, Tsinghua University",
      abstract: "We propose a principled framework for test-time scaling of reasoning agents by adaptively allocating compute across uncertainty estimates.",
      reason: "与你近期关注的 agent reasoning、evaluation 和 test-time scaling 高度匹配。",
      tags: ["核心方向匹配", "近期热点", "可精读"],
      source: "arXiv",
      arxiv_id: "2606.03963",
      url: "https://arxiv.org/abs/2606.03963",
      pdf_url: "https://arxiv.org/pdf/2606.03963"
    },
    {
      number: 2,
      score: 88,
      title: "Multi-Modal Retrieval-Augmented Generation with Structured Memory",
      authors: "S. Park, H. Zhao, R. Kumar · MIT, CMU",
      abstract: "A structured memory module captures hierarchical knowledge across modalities and improves long-context QA.",
      reason: "连接 RAG、知识记忆与多模态问答，可沉淀到 Wiki 主题节点。",
      tags: ["与存储Wiki相关", "系统方法", "可追踪"],
      source: "ICLR",
      url: "https://openreview.net/forum?id=demo-rag"
    },
    {
      number: 3,
      score: 85,
      title: "Learning to Summarize Scientific Papers with Citation-Aware Feedback",
      authors: "J. Martin, P. Singh, X. Wu · University of Washington, Microsoft Research",
      abstract: "Citation-grounded feedback improves factuality and reader alignment for scientific summarization.",
      reason: "适合评估精读报告中的引用质量与可解释性。",
      tags: ["精读价值高", "引用评估"],
      source: "ACL",
      url: "https://doi.org/10.0000/demo-citation"
    },
    {
      number: 4,
      score: 81,
      title: "OpenReview Signals for Personalized Paper Recommendation",
      authors: "L. Torres, K. Nakamura · ETH Zurich, University of Tokyo",
      abstract: "Peer-review signals, including discussion threads, improve early preference ranking for personalized paper selection.",
      reason: "可补充推荐系统的人工反馈和会议源数据策略。",
      tags: ["推荐机制相关", "近期热点"],
      source: "NeurIPS",
      url: "https://openreview.net/forum?id=demo-rec"
    }
  ];

  const demoReports = [
    {
      report_id: "report_reasoning_agents",
      title: "Efficient Test-Time Scaling for Reasoning Agents",
      user_id: "user_demo",
      saved_at: "2026-06-10",
      arxiv_id: "2606.03963",
      status: "已完成",
      snippet: "围绕 test-time scaling、uncertainty routing 与 benchmark 提升展开。",
      report_path: "data/reading_reports/user_demo/2606.03963.md",
      abs_url: "https://arxiv.org/abs/2606.03963",
      pdf_url: "https://arxiv.org/pdf/2606.03963",
      markdown: [
        "# Efficient Test-Time Scaling for Reasoning Agents",
        "## 一句话总结",
        "本文提出一种自适应的测试时扩展策略，在推理不确定性较高的步骤分配更多计算预算，从而提升复杂任务上的稳定性。",
        "## 研究动机",
        "现有 agent 推理系统常把预算均匀分配给所有问题，但不同问题和不同推理步骤的边际收益并不一致。",
        "## 核心方法",
        "- 使用不确定性估计选择需要扩展的推理分支。",
        "- 将结果写入可审计的 reasoning trace。",
        "- 对 benchmark 结果做按任务类型的消融分析。",
        "## 与我的关系",
        "这篇论文可作为 PaperFlow 推荐策略中的“计算预算分配”和“精读优先级”参考，也适合加入 Wiki 的 Agent Memory 条目。"
      ].join("\n\n")
    },
    {
      report_id: "report_structured_memory",
      title: "Multi-Modal Retrieval-Augmented Generation with Structured Memory",
      user_id: "user_demo",
      saved_at: "2026-06-08",
      arxiv_id: "",
      status: "已完成",
      snippet: "把多模态检索和结构化记忆合并到长上下文 QA。",
      report_path: "data/reading_reports/user_demo/structured-memory.md",
      abs_url: "https://openreview.net/forum?id=demo-rag",
      pdf_url: "",
      markdown: [
        "# Multi-Modal RAG with Structured Memory",
        "## 一句话总结",
        "论文将文档、图像和表格证据统一写入层级记忆结构，并在问答时按证据类型检索。",
        "## 核心方法",
        "- 文档块、实体和图像区域分别建索引。",
        "- 通过结构化 memory slot 聚合跨模态证据。",
        "- 回答阶段显式输出引用来源。",
        "## 可落地启发",
        "PaperFlow 的 Wiki 页面可以采用“图谱 + 文档”双视图，右侧保留关联论文和相关概念。"
      ].join("\n\n")
    },
    {
      report_id: "report_citation_feedback",
      title: "Learning to Summarize Scientific Papers with Citation-Aware Feedback",
      user_id: "user_demo",
      saved_at: "2026-06-06",
      arxiv_id: "",
      status: "已完成",
      snippet: "通过 citation-aware feedback 改善科研摘要事实性。",
      report_path: "data/reading_reports/user_demo/citation-feedback.md",
      abs_url: "https://doi.org/10.0000/demo-citation",
      pdf_url: "",
      markdown: [
        "# Citation-Aware Feedback",
        "## 一句话总结",
        "作者把引用覆盖率、主张可追溯性和段落级反馈合并为训练信号。",
        "## 实验结果",
        "在科学论文摘要任务中，事实一致性和引用召回均有明显提升。",
        "## 与我的关系",
        "可用于评估精读报告是否真正引用了论文中的证据，而不是泛化总结。"
      ].join("\n\n")
    }
  ];

  const demoWikiNodes = [
    { id: "结构化记忆", type: "topic", x: 50, y: 50, size: "core", body: "跨论文沉淀的 memory slot、引用关系和上下文片段。" },
    { id: "RAG", type: "topic", x: 36, y: 40, size: "large", body: "围绕检索增强生成、证据召回和回答可追溯的核心主题。" },
    { id: "Agent", type: "topic", x: 65, y: 38, size: "large", body: "连接任务规划、工具调用和长期研究记忆的智能体方向。" },
    { id: "论文流", type: "paper", x: 24, y: 27, size: "medium", body: "每日推荐进入知识库的入口，记录候选、反馈和精读状态。" },
    { id: "精读报告", type: "paper", x: 27, y: 70, size: "medium", body: "从 PDF 和 arXiv 生成的结构化 Markdown 报告。" },
    { id: "知识图谱", type: "method", x: 45, y: 75, size: "medium", body: "将论文、概念、方法、引用和上下文关系连接为本地网络。" },
    { id: "检索评估", type: "method", x: 63, y: 72, size: "medium", body: "评估召回质量、引用准确率和回答可追溯性。" },
    { id: "记忆压缩", type: "method", x: 53, y: 23, size: "small", body: "将长报告压缩为可复用的研究记忆片段。" },
    { id: "引用证据", type: "method", x: 39, y: 19, size: "small", body: "记录段落、公式、图表和报告之间的证据链。" },
    { id: "个性化推荐", type: "frontier", x: 78, y: 24, size: "small", body: "结合画像、反馈和必读规则调整论文排序。" },
    { id: "多模态协作", type: "frontier", x: 80, y: 58, size: "medium", body: "把文本、图表、代码和实验记录纳入同一研究上下文。" },
    { id: "研究前沿", type: "frontier", x: 17, y: 52, size: "small", body: "由最近论文聚合出来的主题漂移和趋势节点。" }
  ];

  const demoWikiEdges = [
    ["结构化记忆", "RAG"],
    ["结构化记忆", "Agent"],
    ["结构化记忆", "知识图谱"],
    ["结构化记忆", "检索评估"],
    ["结构化记忆", "记忆压缩"],
    ["RAG", "引用证据"],
    ["RAG", "研究前沿"],
    ["论文流", "RAG"],
    ["论文流", "研究前沿"],
    ["精读报告", "知识图谱"],
    ["精读报告", "引用证据"],
    ["Agent", "多模态协作"],
    ["Agent", "个性化推荐"],
    ["检索评估", "多模态协作"]
  ].map(([src_id, dst_id]) => ({ src_id, dst_id, relation: "related", weight: 1 }));

  const demoSources = [
    {
      index: 1,
      node_id: "paper:reasoning-agents",
      node_type: "paper",
      title: "Efficient Test-Time Scaling for Reasoning Agents",
      meta: "精读报告 · 高度相关",
      excerpt: "围绕 test-time scaling、uncertainty routing 与 benchmark 提升展开。"
    },
    {
      index: 2,
      node_id: "paper:structured-memory",
      node_type: "paper",
      title: "Multi-Modal RAG with Structured Memory",
      meta: "精读报告 · 高度相关",
      excerpt: "把多模态检索和结构化记忆合并到长上下文 QA。"
    },
    {
      index: 3,
      node_id: "paper:citation-feedback",
      node_type: "paper",
      title: "Learning to Summarize Scientific Papers with Citation-Aware Feedback",
      meta: "精读报告 · 中等相关",
      excerpt: "跨论文沉淀的 memory slot、引用关系和上下文片段。"
    },
    {
      index: 4,
      node_id: "paper:openreview-signals",
      node_type: "paper",
      title: "OpenReview Signals for Personalized Recommendation",
      meta: "候选论文 · 中等相关",
      excerpt: "结合 peer-review signals 改进个性化论文推荐。"
    }
  ];

  const demoProfiles = {
    user_demo: {
      user_id: "user_demo",
      version: "0.2",
      updated_at: "2026-06-10",
      description: "关注科研阅读 agent、结构化记忆、个性化论文推荐和可追溯精读报告。",
      scholar_url: "https://scholar.google.com/citations?user=demo",
      homepage_url: "https://paperflow.local/demo",
      pdf_paths: ["data/papers/demo-profile.pdf"],
      core_directions: {
        "scientific reading agents": 0.92,
        "structured memory": 0.86,
        "personalized recommendation": 0.8
      },
      topic_weights: {
        "RAG": 0.78,
        "agent evaluation": 0.74,
        "citation grounding": 0.69
      },
      must_read: { authors: ["Yoshua Bengio"], institutions: ["Stanford"], keywords: ["agent memory", "scientific discovery"] }
    },
    user_lab: {
      user_id: "user_lab",
      version: "0.1",
      updated_at: "2026-06-09",
      description: "实验室视角，偏向多模态科研工作流、评测基准和论文到知识库的自动归档。",
      core_directions: {
        "multimodal research workflow": 0.84,
        "benchmark evaluation": 0.78,
        "knowledge ingestion": 0.73
      },
      topic_weights: { "workflow automation": 0.82, "offline wiki": 0.76 }
    },
    user_founder: {
      user_id: "user_founder",
      version: "0.1",
      updated_at: "2026-06-08",
      description: "产品和方向判断视角，关注用户反馈、研究机会发现和高价值论文筛选。",
      core_directions: {
        "product-led research": 0.82,
        "user feedback learning": 0.77,
        "opportunity discovery": 0.74
      },
      topic_weights: { "paper triage": 0.8, "research strategy": 0.72 }
    }
  };

  const $ = (id) => document.getElementById(id);

  function todayDateValue() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function dateFromInputValue(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  }

  function selectedDateFetchDays() {
    const today = dateFromInputValue(todayDateValue());
    const selected = dateFromInputValue($("paperDate")?.value || "");
    if (!today || !selected) return Number($("daysInput")?.value || 1);
    if (selected > today) return 1;
    const diffDays = Math.floor((today - selected) / 86400000) + 1;
    return Math.min(14, Math.max(1, diffDays));
  }

  function syncDateControls() {
    const dateInput = $("paperDate");
    const daysInput = $("daysInput");
    const runButton = $("runDailyBtn");
    if (!dateInput || !daysInput || !runButton) return;
    if (state.dailyPolling) {
      runButton.disabled = true;
      runButton.textContent = "后台运行中";
      return;
    }
    const today = todayDateValue();
    if (!dateInput.value) dateInput.value = today;
    if (dateInput.value > today) dateInput.value = today;
    daysInput.value = String(selectedDateFetchDays());
    runButton.disabled = false;
    runButton.textContent = dateInput.value === today ? "拉取今日论文" : "拉取所选日期论文";
  }

  function setDailyTaskState(taskId = "", userId = "", polling = false) {
    state.dailyTaskId = taskId || "";
    state.dailyTaskUserId = userId || "";
    state.dailyPolling = Boolean(polling && taskId);
    syncDateControls();
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function normalizeScore(value) {
    const raw = Number(value);
    if (!Number.isFinite(raw)) return 80;
    const percentage = raw > 0 && raw <= 1 ? raw * 100 : raw;
    return Math.max(0, Math.min(100, Math.round(percentage)));
  }

  function setStatus(message) {
    $("statusText").textContent = message;
  }

  function showFeedbackToast(type, title, detail = "") {
    const toast = $("feedbackToast");
    if (!toast) return;
    window.clearTimeout(state.feedbackTimer);
    toast.className = `feedback-toast ${type || "success"}`;
    toast.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    `;
    toast.hidden = false;
    state.feedbackTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, type === "error" ? 9000 : 6500);
  }

  function showPaperFeedback(type, title, detail = "") {
    const target = $("paperFeedbackResult");
    if (!target) return;
    target.className = `paper-feedback-result ${type || "success"}`;
    target.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    `;
    target.hidden = false;
  }

  function setSubmitButtonsBusy(busy, generateReports = false) {
    const feedbackButton = $("submitFeedbackBtn");
    const readButton = $("submitAndReadBtn");
    if (!feedbackButton || !readButton) return;
    feedbackButton.disabled = busy;
    readButton.disabled = busy;
    feedbackButton.textContent = busy && !generateReports ? "提交中" : "提交反馈";
    readButton.textContent = busy && generateReports ? "生成中" : "提交并精读";
  }

  async function runAction(action, busyText = "处理中") {
    try {
      setStatus(busyText);
      await action();
      setStatus("就绪");
    } catch (error) {
      setStatus("出错");
      console.error(error);
      showFeedbackToast("error", "操作失败", error.message || String(error));
    }
  }

  async function api(path, options = {}) {
    if (DEMO_MODE) return demoApi(path, options);
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "请求失败");
    return data;
  }

  async function demoApi(path, options = {}) {
    await new Promise((resolve) => window.setTimeout(resolve, 90));
    const url = new URL(path, window.location.origin);
    const route = url.pathname;
    const body = options.body ? JSON.parse(options.body) : {};

    if (route === "/api/health") {
      return { ok: true, database_exists: true, database: "demo.db", version: "offline-demo" };
    }
    if (route === "/api/users") {
      return { ok: true, users: ["user_demo", "user_lab", "user_founder"] };
    }
    if (route === "/api/source-options") {
      return {
        ok: true,
        arxiv_categories: [
          { id: "cs.CL", name: "cs.CL" },
          { id: "cs.AI", name: "cs.AI" },
          { id: "cs.IR", name: "cs.IR" },
          { id: "cs.LG", name: "cs.LG" }
        ],
        conferences: [
          { id: "ICLR", name: "ICLR", group: "ML", source: "openreview.net API", venue_id: "ICLR.cc", acceptance_timeline: "1 月底", conference_date: "4-5 月" },
          { id: "NeurIPS", name: "NeurIPS", group: "ML", source: "openreview.net API", venue_id: "NeurIPS.cc", acceptance_timeline: "9 月底", conference_date: "12 月" },
          { id: "ACL", name: "ACL", group: "NLP", source: "openreview / aclanthology", venue_id: "ACL.org", acceptance_timeline: "5 月", conference_date: "7-8 月" },
          { id: "SIGIR", name: "SIGIR", group: "IR", source: "DBLP / ACM DL", venue_id: "SIGIR.org", acceptance_timeline: "4 月", conference_date: "7 月" }
        ],
        journals: [
          { id: "Nature Machine Intelligence", name: "Nature MI" },
          { id: "JMLR", name: "JMLR" },
          { id: "TOIS", name: "TOIS" }
        ]
      };
    }
    if (route === "/api/latest-push" || route === "/api/daily/start") {
      return {
        ok: true,
        task: { task_id: "demo-task", status: "completed" },
        push: {
          push_id: "push_demo_20260610",
          push_time: "2026-06-10 08:00",
          papers: demoPapers,
          metadata: {
            total_fetched: 247,
            paper_count: 35,
            filtered_count: 35
          }
        }
      };
    }
    if (route === "/api/daily/status") {
      return {
        ok: true,
        task: {
          task_id: "demo-task",
          status: "completed",
          push: {
            push_id: "push_demo_20260610",
            push_time: "2026-06-10 08:00",
            papers: demoPapers,
            metadata: { total_fetched: 247, paper_count: 35, filtered_count: 35 }
          }
        }
      };
    }
    if (route === "/api/feedback") {
      return { ok: true, selected_numbers: body.selected_numbers || [], skipped_numbers: body.skipped_numbers || [], later_numbers: body.later_numbers || [] };
    }
    if (route === "/api/submit" || route === "/api/read/arxiv" || route === "/api/read/pdf") {
      return {
        ok: true,
        feedback: {
          selected_numbers: body.selected_numbers || [],
          skipped_numbers: body.skipped_numbers || [],
          later_numbers: body.later_numbers || []
        },
        reports: {
          count: 1,
          created_docs: [
            {
              report_id: "report_reasoning_agents",
              title: body.arxiv_id ? `arXiv ${body.arxiv_id} 精读报告` : "Efficient Test-Time Scaling for Reasoning Agents",
              report_path: "data/reading_reports/user_demo/demo.md",
              pdf_path: "data/papers/demo.pdf",
              url: "https://arxiv.org/abs/2606.03963"
            }
          ]
        }
      };
    }
    if (route === "/api/reports") {
      return { ok: true, count: demoReports.length, source_dirs: ["data/reading_reports/user_demo"], reports: demoReports };
    }
    if (route === "/api/reports/content") {
      return { ok: true, report: demoReports.find((item) => item.report_id === url.searchParams.get("report_id")) || demoReports[0] };
    }
    if (route === "/api/wiki/stats") {
      return { ok: true, nodes: 112, edges: 248, citations: 436, wiki_dir: "data/wiki/user_demo" };
    }
    if (route === "/api/wiki/graph") {
      return { ok: true, nodes: demoWikiNodes.map((node) => ({ ...node, node_id: node.id, title: node.id, node_type: node.type })), edges: demoWikiEdges, source: "demo" };
    }
    if (route === "/api/wiki/search") {
      return {
        ok: true,
        nodes: [
          { node_id: "topic:structured-memory", title: "结构化记忆", node_type: "topic", body: "跨论文沉淀的 memory slot、引用关系和上下文片段。", score: 0.91 },
          { node_id: "method:rag-eval", title: "RAG 评估", node_type: "method", body: "检索召回、引用准确率与回答可追溯性。", score: 0.84 },
          { node_id: "frontier:agent-memory", title: "Agent Memory", node_type: "frontier", body: "用于长期研究助手的个人化记忆机制。", score: 0.78 }
        ]
      };
    }
    if (route === "/api/wiki/ask") {
      return {
        ok: true,
        text: "基于最近的 5 篇论文和 3 个 Wiki 条目，RAG 方向的重点正在从单纯检索转向结构化记忆、引用可追溯和多模态证据融合。[1][2] 建议优先精读 test-time scaling 与 structured memory 两条线索。[3]",
        mode: "wiki",
        retrieval_required: true,
        routing_reason: body.mentions?.length ? "explicit_mention" : "local_research_context",
        citations: demoSources,
        sources: demoSources,
        mentions: body.mentions || [],
        streaming: { provider: false, transport: "desktop-progressive" }
      };
    }
    if (route === "/api/wiki/node") {
      return { ok: true, node: { node_id: body.node_id, title: body.title, body: body.body, node_type: "topic" } };
    }
    if (route === "/api/settings") {
      if ((options.method || "GET").toUpperCase() === "POST") {
        return demoApi("/api/settings");
      }
      return {
        ok: true,
        paths: {
          pdf_dir: "data/papers",
          reading_reports_dir: "data/reading_reports",
          wiki_dir: "data/wiki",
          write_feishu: false,
          wiki_ingest: true
        },
        storage_stats: {
          cache_bytes: 0,
          cache_display: "0B"
        },
        editable_env: {
          PAPERFLOW_LLM_PROVIDER: { value: "openai", masked: false },
          PAPERFLOW_LLM_MODEL: { value: "gpt-4o", masked: false },
          OPENAI_API_KEY: { value: "********", masked: true },
          PAPERFLOW_EMBEDDING_MODEL: { value: "text-embedding-3-large", masked: false },
          PAPERFLOW_MAX_CONCURRENCY: { value: "5", masked: false }
        }
      };
    }
    if (route === "/api/provider-test") {
      return { ok: true, kind: body.kind || "llm", provider: "demo", message: "连接测试通过（demo 模式）" };
    }
    if (route === "/api/export") {
      return { ok: true, format: body.format || "markdown", display_path: `data/desktop_exports/demo.${body.format === "zip" ? "zip" : "md"}`, count: 12 };
    }
    if (route === "/api/profile") {
      const userId = body.user_id || url.searchParams.get("user_id") || state.currentUser;
      const submitted = (options.method || "GET").toUpperCase() === "POST";
      const raw = submitted
        ? {
            ...(demoProfiles[userId] || {}),
            user_id: userId,
            description: body.natural_language || demoProfiles[userId]?.description || "",
            scholar_url: body.scholar_url || demoProfiles[userId]?.scholar_url || "",
            homepage_url: body.homepage_url || demoProfiles[userId]?.homepage_url || "",
            pdf_paths: body.pdf_paths || demoProfiles[userId]?.pdf_paths || []
          }
        : (demoProfiles[userId] || { user_id: userId, description: "" });
      const topDirections = Object.entries(raw.core_directions || {}).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, 8);
      const topTopics = Object.entries(raw.topic_weights || {}).sort((a, b) => Number(b[1]) - Number(a[1])).slice(0, 8);
      return {
        ok: true,
        profile: {
          user_id: raw.user_id,
          version: raw.version,
          updated_at: raw.updated_at,
          core_directions: raw.core_directions || {},
          top_directions: topDirections,
          top_topics: topTopics,
          must_read: raw.must_read || {},
          drift_state: raw.drift_state || {}
        },
        raw
      };
    }
    return { ok: false, error: `Unknown demo API route: ${route}` };
  }

  function setView(name, updateHash = true, options = {}) {
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === name));
    document.querySelectorAll(".rail-item").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
    const active = $(name);
    if (active) {
      $("pageTitle").textContent = active.dataset.title || "";
      $("pageKicker").textContent = active.dataset.kicker || "";
    }
    if (updateHash && window.location.hash.slice(1) !== name) {
      history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${name}`);
    }
    window.scrollTo({ top: 0, left: 0 });
    if (name === "reports" && !options.skipLoad) runAction(() => refreshReports({ keepSelection: true }), "加载报告");
    if (name === "wiki" && !options.skipLoad) runAction(loadWiki, "加载 Wiki");
    if (name === "settings") runAction(loadSettings, "加载设置");
    if (name === "papers") {
      resumeDailyTask().catch((error) => {
        console.error(error);
      });
    }
  }

  function currentUser() {
    return $("userSelect").value || state.currentUser || "user_demo";
  }

  function normalizeUser(raw) {
    if (typeof raw === "string") {
      return { user_id: raw, label: raw, is_current: false, description: "", affiliation: "", has_profile: false, updated_at: "" };
    }
    const userId = raw?.user_id || raw?.id || raw?.name || "";
    const role = raw?.role_name ? `${raw.role_name} · ` : "";
    const label = userId ? `${role}${userId}` : "未命名用户";
    return {
      user_id: userId || label,
      label,
      role_name: raw?.role_name || "",
      description: raw?.description || "",
      affiliation: raw?.affiliation || raw?.institution || raw?.organization || "",
      has_profile: Boolean(raw?.has_profile),
      updated_at: raw?.updated_at || "",
      is_current: Boolean(raw?.is_current)
    };
  }

  async function loadUsers() {
    const data = await api("/api/users");
    state.users = data.users && data.users.length ? data.users.map(normalizeUser) : [normalizeUser("user_demo")];
    const ids = state.users.map((user) => user.user_id);
    const current = state.users.find((user) => user.is_current) || state.users[0];
    if (!ids.includes(state.currentUser)) state.currentUser = current.user_id;
    $("userSelect").innerHTML = state.users.map((user) => `<option value="${escapeHtml(user.user_id)}">${escapeHtml(user.label)}</option>`).join("");
    $("userSelect").value = state.currentUser;
    if ($("profileUserId")) $("profileUserId").value = state.currentUser;
  }

  async function loadHealth() {
    const data = await api("/api/health");
    $("healthText").textContent = DEMO_MODE ? "Demo 离线预览" : data.database_exists ? "运行环境就绪" : "请先初始化";
  }

  function renderChoiceList(id, items) {
    const target = $(id);
    target.className = "choice-list";
    target.innerHTML = items.map((item, index) => {
      const value = item.id || item.name || item;
      const label = item.name || item.id || item;
      const checked = index < 3 ? "checked" : "";
      return `<label class="source-choice"><input type="checkbox" value="${escapeHtml(value)}" ${checked}>${escapeHtml(label)}</label>`;
    }).join("");
  }

  async function loadSourceOptions() {
    if (state.sourceOptionsLoaded) return;
    const data = await api("/api/source-options");
    state.sourceOptions = data;
    renderChoiceList("arxivCategories", data.arxiv_categories || []);
    renderChoiceList("conferenceSources", data.conferences || []);
    renderChoiceList("journalSources", data.journals || []);
    state.sourceOptionsLoaded = true;
  }

  function selectedSourceValues(id) {
    return Array.from($(id).querySelectorAll("input:checked")).map((input) => input.value);
  }

  function collectDailyOptions() {
    return {
      arxiv_categories: selectedSourceValues("arxivCategories"),
      conferences: selectedSourceValues("conferenceSources"),
      journals: selectedSourceValues("journalSources")
    };
  }

  function paperReportKey(number, pushId = state.push?.push_id) {
    return [currentUser(), pushId || "no-push", Number(number)].join("::");
  }

  function renderPush(push) {
    state.push = push;
    state.selected.clear();
    state.skipped.clear();
    state.later.clear();
    const papers = push?.papers || [];
    const metadata = push?.metadata || {};
    $("candidateStat").textContent = metadata.total_fetched ?? metadata.fetched_count ?? papers.length ?? 0;
    $("filteredStat").textContent = metadata.paper_count ?? metadata.filtered_count ?? metadata.ranked_count ?? papers.length ?? 0;
    $("latestPushStat").textContent = papers.length || "-";
    $("readingQueueStat").textContent = "0";
    $("pushMeta").textContent = push?.push_id
      ? `批次 ${push.push_id} · ${push.push_time || "本地时间"} · ${papers.length} 篇推荐`
      : "尚未加载推荐批次。";
    if (!papers.length) {
      $("paperList").className = "paper-list empty";
      $("paperList").textContent = "暂无推荐论文。";
      updateSelectionSummary();
      return;
    }
    $("paperList").className = "paper-list";
    $("paperList").innerHTML = papers.map((paper, index) => {
      const number = Number(paper.number || index + 1);
      const reportKey = paperReportKey(number, push?.push_id);
      const reportId = state.paperReports.get(reportKey);
      const isReading = state.paperReading.has(reportKey);
      const score = normalizeScore(paper.score ?? paper.relevance ?? paper.relevance_score ?? 80);
      const tags = paper.tags || [paper.source || "论文", "画像匹配"];
      return `
        <article class="paper-card" data-paper-number="${number}">
          <div class="score-ring" style="--score: ${Math.min(score, 100)}%">${score}%</div>
          <div class="paper-content">
            <h3>${escapeHtml(paper.title || "Untitled Paper")}</h3>
            <p class="paper-authors">${escapeHtml(Array.isArray(paper.authors) ? paper.authors.join(", ") : (paper.authors || paper.author || "作者信息待补充"))}</p>
            <p class="paper-abstract">${escapeHtml(paper.abstract || paper.summary || "")}</p>
            <div class="paper-tags">
              ${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
            </div>
          </div>
          <div class="paper-actions">
            <button data-action="read" data-number="${number}" class="${reportId ? "ready" : ""} ${isReading ? "loading" : ""}" type="button" ${isReading ? "disabled" : ""}>${isReading ? "加载中" : reportId ? "精读报告" : "精读"}</button>
            <button data-action="skip" data-number="${number}" type="button">不感兴趣</button>
            <button data-action="later" data-number="${number}" type="button">稍后看</button>
          </div>
        </article>`;
    }).join("");
    updateSelectionSummary();
  }

  async function loadLatestPush() {
    const data = await api(`/api/latest-push?user_id=${encodeURIComponent(currentUser())}`);
    renderPush(data.push || data.result?.push || data);
  }

  async function runDaily() {
    syncDateControls();
    if (state.dailyPolling && state.dailyTaskId) {
      showFeedbackToast("success", "论文拉取仍在后台运行", `任务 ${state.dailyTaskId} 会在完成后自动刷新论文流。`);
      return;
    }
    const days = selectedDateFetchDays();
    $("daysInput").value = String(days);
    const options = collectDailyOptions();
    const userId = currentUser();
    const runButton = $("runDailyBtn");
    runButton.disabled = true;
    runButton.textContent = "后台运行中";
    const pollToken = ++state.dailyPollToken;
    try {
      const data = await api("/api/daily/start", {
        method: "POST",
        body: JSON.stringify({ user_id: userId, days, target_date: $("paperDate").value, limit_per_source: 100, ...options })
      });
      const taskId = data.task?.task_id || "";
      if (taskId) setDailyTaskState(taskId, userId, true);
      if (data.task) renderDailyTaskStatus(data.task);
      await pollDailyTask(taskId, data.push, userId, pollToken);
    } finally {
      if (pollToken === state.dailyPollToken) {
        setDailyTaskState("", "", false);
      }
    }
  }

  function renderDailyTaskStatus(task) {
    if (!task) return;
    if (task.status === "completed" && task.push) {
      renderPush(task.push);
      return;
    }
    const preview = task.preview_push || {};
    const metadata = preview.metadata || {};
    state.push = null;
    state.selected.clear();
    state.skipped.clear();
    state.later.clear();
    $("candidateStat").textContent = task.fetched_count ?? metadata.total_fetched ?? metadata.fetched_count ?? 0;
    $("filteredStat").textContent = task.ranked_count ?? metadata.ranked_count ?? 0;
    $("latestPushStat").textContent = "-";
    $("readingQueueStat").textContent = "0";
    $("pushMeta").textContent = `任务 ${task.task_id || ""} · ${task.status || "queued"} · ${task.progress_phase || "等待后端返回进度"}`;
    $("paperList").className = "paper-list empty syncing";
    $("paperList").textContent = "后台仍在拉取和排序论文，完成后会显示正式推荐列表。";
    updateSelectionSummary();
  }

  async function pollDailyTask(taskId, immediatePush = null, userId = currentUser(), pollToken = state.dailyPollToken) {
    if (!taskId) {
      renderPush(immediatePush || { papers: [], metadata: { total_fetched: 0, paper_count: 0 } });
      await loadWiki();
      return;
    }
    setDailyTaskState(taskId, userId, true);
    while (pollToken === state.dailyPollToken) {
      const data = await api(`/api/daily/status?task_id=${encodeURIComponent(taskId)}&user_id=${encodeURIComponent(userId)}`);
      if (pollToken !== state.dailyPollToken || currentUser() !== userId) return;
      const task = data.task;
      if (!task) break;
      if (task.status === "completed") {
        renderPush(task.push || { papers: [], metadata: { total_fetched: 0, paper_count: 0 } });
        await loadWiki();
        return;
      }
      if (task.status === "failed") {
        throw new Error(task.error || "论文拉取失败");
      }
      renderDailyTaskStatus(task);
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }
  }

  async function resumeDailyTask() {
    if (state.dailyPolling) return;
    const userId = currentUser();
    const data = await api(`/api/daily/status?user_id=${encodeURIComponent(userId)}`);
    const task = data.task;
    if (!task || !["queued", "running"].includes(task.status)) return;
    const pollToken = ++state.dailyPollToken;
    setDailyTaskState(task.task_id, userId, true);
    renderDailyTaskStatus(task);
    pollDailyTask(task.task_id, null, userId, pollToken).catch((error) => {
      if (pollToken !== state.dailyPollToken) return;
      setDailyTaskState("", "", false);
      showFeedbackToast("error", "论文拉取失败", error.message || String(error));
    }).finally(() => {
      if (pollToken === state.dailyPollToken) setDailyTaskState("", "", false);
    });
  }

  function updateSelectionSummary() {
    $("selectedStat").textContent = state.selected.size;
    $("readingQueueStat").textContent = state.selected.size;
    $("selectionSummary").textContent = `${state.selected.size} 篇待精读，${state.skipped.size} 篇不感兴趣，${state.later.size} 篇稍后看`;
    document.querySelectorAll(".paper-actions button").forEach((button) => {
      const number = Number(button.dataset.number);
      button.classList.toggle("active", button.dataset.action === "skip" && state.skipped.has(number));
      button.classList.toggle("active", button.dataset.action === "later" && state.later.has(number));
    });
    updateReadButtons();
  }

  function updateReadButtons() {
    document.querySelectorAll('.paper-actions button[data-action="read"]').forEach((button) => {
      const number = Number(button.dataset.number);
      const reportKey = paperReportKey(number);
      const reportId = state.paperReports.get(reportKey);
      const isReading = state.paperReading.has(reportKey);
      button.disabled = isReading;
      button.textContent = isReading ? "加载中" : reportId ? "精读报告" : "精读";
      button.classList.toggle("loading", isReading);
      button.classList.toggle("ready", Boolean(reportId) && !isReading);
    });
  }

  function itemCount(value) {
    return Array.isArray(value) ? value.length : 0;
  }

  function submitResultMessage(data, generateReports) {
    const feedback = data.feedback || data || {};
    const selectedCount = itemCount(feedback.selected_numbers);
    const skippedCount = itemCount(feedback.skipped_numbers);
    const laterCount = itemCount(feedback.later_numbers);
    const totalFeedback = selectedCount + skippedCount + laterCount;
    const reportCount = Number(data.reports?.count || data.reports?.created_docs?.length || 0);
    const wikiBackfilled = Number(data.reports?.wiki_backfilled || 0);
    const feishuWarning = data.reports?.feishu_warning || "";

    if (!totalFeedback && !reportCount) {
      return {
        type: "warning",
        title: "没有新的反馈",
        detail: "请选择精读、不感兴趣或稍后看后再提交。"
      };
    }

    const title = generateReports
      ? reportCount
        ? `反馈已提交，已生成 ${reportCount} 篇精读报告`
        : "反馈已提交，未生成新报告"
      : "反馈已提交";
    const detailParts = [];
    if (totalFeedback) {
      detailParts.push(`已写入本地反馈：精读 ${selectedCount} / 不感兴趣 ${skippedCount} / 稍后看 ${laterCount}`);
      detailParts.push("用户画像和 Wiki 会根据这些信号更新");
    }
    if (wikiBackfilled) detailParts.push(`已补写 ${wikiBackfilled} 条精读报告到 Wiki`);
    if (feishuWarning) detailParts.push(feishuWarning);
    if (!detailParts.length && reportCount) detailParts.push("报告已进入精读报告库");
    return {
      type: feishuWarning ? "warning" : "success",
      title,
      detail: `${detailParts.join("。")}。`
    };
  }

  function showSubmitResult(data, generateReports) {
    const result = submitResultMessage(data, generateReports);
    showPaperFeedback(result.type, result.title, result.detail);
    showFeedbackToast(result.type, result.title, result.detail);
  }

  async function openReport(reportId) {
    if (!reportId) return;
    setView("reports", true, { skipLoad: true });
    await refreshReports({ keepSelection: false, activeReportId: reportId });
  }

  async function readSinglePaper(number) {
    if (!state.push?.push_id) throw new Error("请先加载推荐批次");
    const reportKey = paperReportKey(number);
    const existingReportId = state.paperReports.get(reportKey);
    if (existingReportId) {
      await openReport(existingReportId);
      return;
    }

    state.paperReading.add(reportKey);
    state.selected.add(number);
    state.skipped.delete(number);
    state.later.delete(number);
    updateSelectionSummary();

    try {
      const data = await api("/api/submit", {
        method: "POST",
        body: JSON.stringify({
          user_id: currentUser(),
          push_id: state.push.push_id,
          selected_numbers: [number],
          skipped_numbers: [],
          later_numbers: [],
          generate_reports: true,
          write_feishu: $("writeFeishuReports")?.checked || false
        })
      });
      const doc = data.reports?.created_docs?.[0];
      if (!doc?.report_id) throw new Error("精读报告已生成，但后端没有返回 report_id");
      state.paperReports.set(reportKey, doc.report_id);
      await loadWiki();
    } finally {
      state.paperReading.delete(reportKey);
      updateSelectionSummary();
    }
  }

  async function submitFeedback(generateReports) {
    if (!state.push?.push_id) {
      showPaperFeedback("error", "无法提交反馈", "请先拉取今日论文或加载最近一次推荐批次。");
      throw new Error("请先加载推荐批次");
    }
    const endpoint = generateReports ? "/api/submit" : "/api/feedback";
    setSubmitButtonsBusy(true, generateReports);
    showPaperFeedback(
      "pending",
      generateReports ? "正在提交反馈并生成精读报告" : "正在提交反馈",
      "正在写入本地反馈、更新用户方向，并准备同步到 Wiki。"
    );
    try {
      const data = await api(endpoint, {
        method: "POST",
        body: JSON.stringify({
          user_id: currentUser(),
          push_id: state.push.push_id,
          selected_numbers: Array.from(state.selected),
          skipped_numbers: Array.from(state.skipped),
          later_numbers: Array.from(state.later),
          generate_reports: generateReports,
          write_feishu: $("writeFeishuReports")?.checked || false
        })
      });
      showSubmitResult(data, generateReports);
      await loadWiki();
      if (generateReports) {
        const docs = data.reports?.created_docs || [];
        if (docs[0]?.report_id) {
          await openReport(docs[0].report_id);
        } else {
          setView("reports");
        }
      }
    } catch (error) {
      showPaperFeedback("error", "反馈提交失败", error.message || String(error));
      throw error;
    } finally {
      setSubmitButtonsBusy(false, generateReports);
    }
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    const html = [];
    let inList = false;
    for (const line of lines) {
      if (line.startsWith("### ")) {
        if (inList) html.push("</ul>");
        inList = false;
        html.push(`<h3>${escapeHtml(line.slice(4))}</h3>`);
      } else if (line.startsWith("## ")) {
        if (inList) html.push("</ul>");
        inList = false;
        html.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
      } else if (line.startsWith("# ")) {
        if (inList) html.push("</ul>");
        inList = false;
        html.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
      } else if (line.startsWith("- ")) {
        if (!inList) html.push("<ul>");
        inList = true;
        html.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      } else if (line.trim()) {
        if (inList) html.push("</ul>");
        inList = false;
        html.push(`<p>${escapeHtml(line)}</p>`);
      }
    }
    if (inList) html.push("</ul>");
    return html.join("");
  }

  function renderReportList(reports, activeId = "") {
    const target = $("reportsList");
    if (!reports.length) {
      target.className = "reports-list empty";
      target.textContent = "暂无报告。";
      return;
    }
    target.className = "reports-list";
    target.innerHTML = reports.map((report) => `
      <button class="report-row ${report.report_id === activeId ? "active" : ""}" data-report-id="${escapeHtml(report.report_id)}" type="button">
        <h3>${escapeHtml(report.title || "精读报告")}</h3>
        <p>${escapeHtml(report.saved_at || "")} · ${escapeHtml(report.status || "已完成")}</p>
        <p>${escapeHtml(report.snippet || report.report_path || "")}</p>
      </button>
    `).join("");
  }

  async function refreshReports(options = {}) {
    const scopedUser = $("reportsCurrentOnly").checked ? currentUser() : "";
    const query = $("reportQuery").value.trim();
    const days = $("reportDays").value || "30";
    const date = $("reportDate").value || "";
    const data = await api(`/api/reports?user_id=${encodeURIComponent(scopedUser)}&q=${encodeURIComponent(query)}&days=${days}&date=${encodeURIComponent(date)}&limit=120`);
    state.reports = data.reports || [];
    $("reportSources").textContent = (data.source_dirs || []).length
      ? `报告目录: ${(data.source_dirs || []).join(" | ")} · 数量 ${data.count || state.reports.length}`
      : `数量 ${data.count || state.reports.length}`;
    const activeId = options.activeReportId || (options.keepSelection && state.currentReport ? state.currentReport.report_id : state.reports[0]?.report_id || "");
    renderReportList(state.reports, activeId);
    if (activeId) await loadReportContent(activeId, true);
  }

  function setReportLinks(report) {
    const map = {
      openReportAbsBtn: report.abs_url || report.url || "",
      openReportPdfBtn: report.pdf_url || "",
      openReportDocBtn: report.doc_url || "",
      copyReportPathBtn: report.report_path || ""
    };
    Object.entries(map).forEach(([id, value]) => {
      const button = $(id);
      button.disabled = !value;
      button.dataset.href = value;
    });
  }

  async function loadReportContent(reportId, silent = false) {
    if (!reportId) return;
    const data = await api(`/api/reports/content?report_id=${encodeURIComponent(reportId)}`);
    const report = data.report;
    if (!report) {
      if (!silent) throw new Error("报告不存在");
      return;
    }
    state.currentReport = report;
    renderReportList(state.reports, report.report_id);
    $("reportViewerTitle").textContent = report.title || "精读报告";
    $("reportViewerMeta").textContent = [report.user_id, report.saved_at, report.report_path].filter(Boolean).join(" · ");
    $("reportViewerBody").className = "markdown-body";
    $("reportViewerBody").innerHTML = renderMarkdown(report.markdown || "");
    setReportLinks(report);
  }

  async function directRead(kind) {
    const payload = {
      user_id: currentUser(),
      write_feishu: kind === "pdf" ? $("directPdfWriteFeishu").checked : $("directWriteFeishu").checked
    };
    let route = "/api/read/arxiv";
    if (kind === "arxiv") {
      const raw = $("directArxivId").value.trim();
      payload.arxiv_id = raw.replace(/^https?:\/\/arxiv\.org\/abs\//, "");
    } else {
      route = "/api/read/pdf";
      payload.pdf_path = $("directPdfPath").value.trim();
      payload.title = $("directPdfTitle").value.trim();
    }
    const data = await api(route, { method: "POST", body: JSON.stringify(payload) });
    const doc = data.reports?.created_docs?.[0];
    if (doc?.report_id) await openReport(doc.report_id);
    await loadWiki();
  }

  function graphId(node) {
    const source = node || {};
    return String(source.node_id || source.id || source.title || "node");
  }

  function graphTitle(node) {
    const source = node || {};
    return String(source.title || source.id || source.node_id || "知识条目");
  }

  function graphBody(node) {
    const source = node || {};
    return String(source.body || source.snippet || "");
  }

  function graphType(node) {
    const source = node || {};
    const raw = String(source.node_type || source.type || "topic").toLowerCase();
    if (raw === "paper") return "paper";
    if (raw === "section") return "method";
    if (raw === "trajectory" || raw === "profile") return "frontier";
    if (raw === "method" || raw === "frontier" || raw === "topic") return raw;
    return "topic";
  }

  function graphTypeLabel(node) {
    const type = graphType(node);
    if (type === "method") return "方法";
    if (type === "paper") return "论文/报告";
    if (type === "frontier") return "前沿";
    return "概念";
  }

  function normalizeGraphEdge(edge) {
    if (Array.isArray(edge)) {
      return { src_id: String(edge[0] || ""), dst_id: String(edge[1] || ""), relation: "related", weight: 1 };
    }
    return {
      src_id: String(edge.src_id || edge.source || edge.from || ""),
      dst_id: String(edge.dst_id || edge.target || edge.to || ""),
      relation: String(edge.relation || "related"),
      weight: Number(edge.weight || 1),
      metadata: edge.metadata || {}
    };
  }

  function graphWeight(edge) {
    const weight = Number(edge?.weight);
    if (!Number.isFinite(weight)) return 1;
    return Math.max(0.08, Math.min(1.6, weight));
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function graphAnchor(node) {
    const type = graphType(node);
    if (type === "method") return { x: 64, y: 42 };
    if (type === "paper") return { x: 46, y: 74 };
    if (type === "frontier") return { x: 74, y: 30 };
    return { x: 34, y: 42 };
  }

  function graphDegreeMap(nodes, edges) {
    const degree = Object.fromEntries(nodes.map((node) => [graphId(node), 0]));
    edges.forEach((edge) => {
      degree[edge.src_id] = (degree[edge.src_id] || 0) + graphWeight(edge);
      degree[edge.dst_id] = (degree[edge.dst_id] || 0) + graphWeight(edge);
    });
    return degree;
  }

  function uniqueGraphNodes(nodes) {
    const seen = new Set();
    return (nodes || []).filter((node) => {
      const id = graphId(node);
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }

  const keywordStopWords = new Set([
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were", "into", "across", "using", "used",
    "based", "paper", "papers", "model", "models", "method", "methods", "task", "tasks", "data", "study",
    "analysis", "approach", "experiments", "future", "directions", "summary", "related", "work", "problem",
    "abstract", "legacy", "reading", "plan", "tldr", "cs", "cl", "ai", "lg", "ir"
  ]);

  const phraseAliases = [
    { label: "Deep Search Agent", patterns: [/deep search/i, /search agents?/i, /shortcut-resistant search/i] },
    { label: "多模态推理", patterns: [/multimodal/i, /multi-modal/i, /long-video understanding/i, /contextual reasoning/i] },
    { label: "推理泛化", patterns: [/reasoning generalization/i, /verifiable environments?/i, /recursive composition/i] },
    { label: "视觉语言模型", patterns: [/vision-language/i, /visual grounding/i, /visual token/i, /token routing/i] },
    { label: "推理效率", patterns: [/inference efficiency/i, /kv-cache/i, /cache compress/i, /token reduction/i] },
    { label: "蛋白结构检索", patterns: [/protein/i, /structural motif/i, /protein universe/i] },
    { label: "基因编辑", patterns: [/genome engineering/i, /prime editing/i, /monocots/i] },
    { label: "强化学习", patterns: [/reinforcement learning/i] },
    { label: "开源模型", patterns: [/open-source/i, /closed-source/i] }
  ];

  const topicPositions = [
    { x: 30, y: 36, size: "large" },
    { x: 70, y: 36, size: "large" },
    { x: 28, y: 58, size: "medium" },
    { x: 72, y: 58, size: "medium" }
  ];
  const methodPositions = [
    { x: 43, y: 25, size: "small" },
    { x: 57, y: 25, size: "small" },
    { x: 84, y: 48, size: "small" }
  ];
  const paperPositions = [
    { x: 22, y: 77, size: "medium" },
    { x: 50, y: 82, size: "medium" },
    { x: 78, y: 77, size: "medium" }
  ];

  function slugLabel(label) {
    return String(label || "node")
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40) || "node";
  }

  function titleCaseLabel(label) {
    return String(label || "")
      .split(/[\s-]+/)
      .filter(Boolean)
      .slice(0, 3)
      .map((word) => word.length <= 3 ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1))
      .join(" ");
  }

  function shortGraphTitle(title, maxLength = 22) {
    const normalized = String(title || "知识条目").replace(/\s+/g, " ").trim();
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized;
  }

  function nodeSearchText(node) {
    return [graphTitle(node), graphBody(node), node?.keywords, node?.node_type, graphId(node)]
      .filter(Boolean)
      .join(" ");
  }

  function tokenizeKnowledgeText(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff-]+/g, " ")
      .split(/\s+/)
      .map((token) => token.trim())
      .filter((token) => token.length > 2 && !keywordStopWords.has(token) && !/^\d+$/.test(token));
  }

  function aliasLabelsForText(text) {
    return phraseAliases
      .filter((alias) => alias.patterns.some((pattern) => pattern.test(text)))
      .map((alias) => alias.label);
  }

  function candidateLabelsForNode(node) {
    const text = nodeSearchText(node);
    const labels = new Set(aliasLabelsForText(text));
    const tokens = tokenizeKnowledgeText([node?.keywords, graphTitle(node)].filter(Boolean).join(" "));
    for (let index = 0; index < tokens.length; index += 1) {
      const one = tokens[index];
      const two = [tokens[index], tokens[index + 1]].filter(Boolean).join(" ");
      const three = [tokens[index], tokens[index + 1], tokens[index + 2]].filter(Boolean).join(" ");
      if (one && ["agent", "reasoning", "retrieval", "multimodal", "embedding", "routing"].includes(one)) {
        labels.add(titleCaseLabel(one));
      }
      if (two && two.length <= 34) labels.add(titleCaseLabel(two));
      if (three && three.length <= 42 && index % 2 === 0) labels.add(titleCaseLabel(three));
    }
    return Array.from(labels)
      .filter((label) => label && label.length >= 3 && !/^(Q\d|TLDR)$/i.test(label))
      .slice(0, 8);
  }

  function conceptEntriesFromGraph(sourceNodes, sourceEdges) {
    const degree = graphDegreeMap(sourceNodes, sourceEdges);
    const entries = new Map();
    sourceNodes.forEach((node) => {
      const nodeId = graphId(node);
      const type = graphType(node);
      const base = type === "paper" ? 2 : type === "frontier" ? 1.3 : type === "method" ? 0.9 : 1;
      candidateLabelsForNode(node).forEach((label, index) => {
        if (!entries.has(label)) {
          entries.set(label, { label, score: 0, nodeIds: new Set(), nodes: [] });
        }
        const entry = entries.get(label);
        entry.score += base + Math.min(2.5, degree[nodeId] || 0) * 0.18 + (8 - index) * 0.04;
        entry.nodeIds.add(nodeId);
        entry.nodes.push(node);
      });
    });
    return dedupeConceptEntries(Array.from(entries.values()).sort((a, b) => b.score - a.score));
  }

  function dedupeConceptEntries(entries) {
    const selected = [];
    entries.forEach((entry) => {
      const key = entry.label.toLowerCase();
      const overlaps = selected.some((item) => {
        const existing = item.label.toLowerCase();
        return existing.includes(key) || key.includes(existing);
      });
      if (!overlaps) selected.push(entry);
    });
    return selected;
  }

  function paperScore(node, degree) {
    const id = graphId(node);
    return (degree[id] || 0) + Number(node.score || 0) + (graphBody(node) ? 0.2 : 0);
  }

  function topPaperNodes(sourceNodes, sourceEdges, limit = 4) {
    const degree = graphDegreeMap(sourceNodes, sourceEdges);
    return sourceNodes
      .filter((node) => graphType(node) === "paper")
      .sort((a, b) => paperScore(b, degree) - paperScore(a, degree))
      .slice(0, limit);
  }

  function relatedPapersForEntry(entry, sourceById, sourceEdges, fallbackPapers = []) {
    const relatedIds = new Set(entry?.nodeIds || []);
    for (let depth = 0; depth < 2; depth += 1) {
      sourceEdges.forEach((edge) => {
        if (relatedIds.has(edge.src_id)) relatedIds.add(edge.dst_id);
        if (relatedIds.has(edge.dst_id)) relatedIds.add(edge.src_id);
      });
    }
    return uniqueGraphNodes([
      ...Array.from(relatedIds).map((id) => sourceById[id]).filter((node) => node && graphType(node) === "paper"),
      ...fallbackPapers
    ]).slice(0, 4);
  }

  function architectureBody(title, sourceNodes, sourceEdges, entries, topPapers) {
    const counts = {
      paper: sourceNodes.filter((node) => graphType(node) === "paper").length,
      section: sourceNodes.filter((node) => graphType(node) === "method").length,
      profile: sourceNodes.filter((node) => graphType(node) === "frontier").length
    };
    const themes = entries.slice(0, 5).map((entry) => entry.label).join("、") || "暂无稳定主题";
    const papers = topPapers.slice(0, 3).map((paper) => `- ${graphTitle(paper)}`).join("\n") || "- 暂无论文证据";
    return [
      "## 知识库架构",
      `当前 Wiki 从 ${sourceNodes.length} 个知识节点和 ${sourceEdges.length} 条关系中整理出这张架构图。`,
      "## 当前主线",
      themes,
      "## 证据来源",
      `- 精读论文：${counts.paper} 篇`,
      `- 章节/方法片段：${counts.section} 个`,
      `- 用户方向节点：${counts.profile} 个`,
      "## 代表论文",
      papers
    ].join("\n");
  }

  function topicBody(entry, relatedPapers) {
    const papers = relatedPapers.map((paper) => `- ${graphTitle(paper)}`).join("\n") || "- 暂无直接论文证据";
    return [
      `## ${entry.label}`,
      `这是从 ${entry.nodeIds.size} 个 Wiki 条目中抽取出的知识库主题，不是固定模板节点。`,
      "## 关联证据",
      papers,
      "## 展示意义",
      "用于帮助用户快速理解当前知识库的研究重心，并继续跳转到论文、章节和精读报告。"
    ].join("\n");
  }

  function userDirectionBody(userNodes, topPapers, entries) {
    const signals = userNodes.flatMap((node) => String(node.keywords || "").split(/[,\s]+/)).filter(Boolean).slice(0, 8);
    const papers = topPapers.slice(0, 3).map((paper) => `- ${graphTitle(paper)}`).join("\n") || "- 暂无精读记录";
    return [
      "## 用户方向",
      "这里汇总用户反馈、精读记录、画像节点和兴趣漂移，用来解释为什么这些主题被放在图谱中心。",
      "## 当前信号",
      signals.length ? signals.join("、") : entries.slice(0, 4).map((entry) => entry.label).join("、") || "暂无稳定信号",
      "## 最近证据",
      papers
    ].join("\n");
  }

  function buildWikiMap(nodes, edges) {
    const sourceNodes = (nodes || []).filter((node) => graphId(node).trim());
    const sourceEdges = (edges || []).map(normalizeGraphEdge);
    const sourceById = Object.fromEntries(sourceNodes.map((node) => [graphId(node), node]));
    const entries = conceptEntriesFromGraph(sourceNodes, sourceEdges);
    const topPapers = topPaperNodes(sourceNodes, sourceEdges, 4);
    const userNodes = sourceNodes.filter((node) => graphType(node) === "frontier" || graphId(node).startsWith("user:"));

    if (!sourceNodes.length) {
      return { nodes: [], edges: [], sourceNodes, sourceEdges, byId: {} };
    }

    const coreNode = {
      id: "architecture:core",
      node_id: "architecture:core",
      title: "知识库架构",
      node_type: "topic",
      type: "topic",
      x: 50,
      y: 49,
      size: "core",
      body: architectureBody("知识库架构", sourceNodes, sourceEdges, entries, topPapers),
      real_node_id: "",
      source_count: sourceNodes.length,
      related_papers: topPapers
    };

    const userNode = {
      id: "architecture:user-direction",
      node_id: "architecture:user-direction",
      title: "用户方向",
      node_type: "frontier",
      type: "frontier",
      x: 50,
      y: 72,
      size: "medium",
      body: userDirectionBody(userNodes, topPapers, entries),
      real_node_id: "",
      source_count: userNodes.length,
      related_papers: topPapers
    };

    const topicEntries = entries.slice(0, 4);
    const topicLabels = new Set(topicEntries.map((entry) => entry.label));
    const methodEntries = entries
      .filter((entry) => !topicLabels.has(entry.label))
      .filter((entry) => /(search|routing|editing|cache|efficiency|grounding|learning|检索|编辑|效率|推理)/i.test(entry.label))
      .concat(entries.filter((entry) => !topicLabels.has(entry.label)))
      .filter((entry, index, arr) => arr.findIndex((item) => item.label === entry.label) === index)
      .slice(0, 3);

    const topicNodes = topicEntries.map((entry, index) => {
      const position = topicPositions[index] || topicPositions[topicPositions.length - 1];
      const relatedPapers = relatedPapersForEntry(entry, sourceById, sourceEdges, topPapers);
      return {
        id: `architecture:topic:${slugLabel(entry.label)}`,
        node_id: `architecture:topic:${slugLabel(entry.label)}`,
        title: entry.label,
        node_type: "topic",
        type: "topic",
        x: position.x,
        y: position.y,
        size: position.size,
        body: topicBody(entry, relatedPapers),
        real_node_id: "",
        source_count: entry.nodeIds.size,
        related_papers: relatedPapers
      };
    });

    const methodNodes = methodEntries.map((entry, index) => {
      const position = methodPositions[index] || methodPositions[methodPositions.length - 1];
      const relatedPapers = relatedPapersForEntry(entry, sourceById, sourceEdges, topPapers);
      return {
        id: `architecture:method:${slugLabel(entry.label)}`,
        node_id: `architecture:method:${slugLabel(entry.label)}`,
        title: entry.label,
        node_type: "method",
        type: "method",
        x: position.x,
        y: position.y,
        size: position.size,
        body: topicBody(entry, relatedPapers),
        real_node_id: "",
        source_count: entry.nodeIds.size,
        related_papers: relatedPapers
      };
    });

    const paperNodes = topPapers.slice(0, 3).map((paper, index) => {
      const position = paperPositions[index] || paperPositions[paperPositions.length - 1];
      return {
        ...paper,
        id: graphId(paper),
        node_id: graphId(paper),
        title: graphTitle(paper),
        node_type: "paper",
        type: "paper",
        x: position.x,
        y: position.y,
        size: position.size,
        body: graphBody(paper) || `这篇论文是当前知识库中的核心证据：${graphTitle(paper)}`,
        real_node_id: graphId(paper),
        source_count: 1,
        related_papers: [paper]
      };
    });

    const mapNodes = [coreNode, ...topicNodes, ...methodNodes, userNode, ...paperNodes];
    const mapEdges = [
      { src_id: userNode.id, dst_id: coreNode.id, relation: "用户方向", weight: 1.2 },
      ...topicNodes.map((node) => ({ src_id: coreNode.id, dst_id: node.id, relation: "主题", weight: 1.1 })),
      ...methodNodes.map((node) => ({ src_id: coreNode.id, dst_id: node.id, relation: "方法", weight: 0.85 })),
      ...paperNodes.map((node, index) => ({
        src_id: topicNodes[index % Math.max(1, topicNodes.length)]?.id || coreNode.id,
        dst_id: node.id,
        relation: "论文证据",
        weight: 0.75
      }))
    ];

    return {
      nodes: mapNodes,
      edges: mapEdges,
      sourceNodes,
      sourceEdges,
      byId: Object.fromEntries(mapNodes.map((node) => [node.id, node]))
    };
  }

  function layoutGraph(nodes, edges) {
    const map = buildWikiMap(nodes, edges);
    state.wikiMap = map;
    return {
      nodes: map.nodes.map((node) => ({ ...node, x: node.x, y: node.y, type: node.type, size: node.size })),
      edges: map.edges,
      centerId: state.currentWikiNodeId && map.byId[state.currentWikiNodeId] ? state.currentWikiNodeId : "architecture:core",
      sourceCount: map.sourceNodes.length,
      sourceEdgeCount: map.sourceEdges.length
    };
  }

  function renderWikiGraph() {
    const target = $("wikiGraph");
    const graph = state.wikiGraph || {};
    const hasBackendGraph = Boolean(graph.nodes?.length);
    const graphNodes = hasBackendGraph ? graph.nodes : state.wikiNodes.length ? state.wikiNodes : DEMO_MODE ? demoWikiNodes : [];
    const graphEdges = hasBackendGraph ? graph.edges || [] : DEMO_MODE ? demoWikiEdges : [];
    const layout = layoutGraph(graphNodes, graphEdges);
    if (!layout.nodes.length) {
      target.innerHTML = `
        <div class="wiki-empty-state">
          <strong>暂无可绘制的 Wiki 图谱</strong>
          <p>先生成精读报告或提交论文反馈，后端会把论文、章节、方法和用户画像写入本地 Wiki。</p>
        </div>
      `;
      return;
    }
    const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
    const lineHtml = layout.edges.map((edge, index) => {
      const a = byId[String(edge.src_id)];
      const b = byId[String(edge.dst_id)];
      if (!a || !b) return "";
      const weightClass = graphWeight(edge) >= 0.78 || a.id === layout.centerId || b.id === layout.centerId
        ? "strong"
        : graphWeight(edge) >= 0.35 ? "medium" : "light";
      const curve = index % 2 === 0 ? 4 : -4;
      const midX = (a.x + b.x) / 2 + curve;
      const midY = (a.y + b.y) / 2 - curve;
      return `<path class="graph-svg-link ${weightClass}" d="M ${a.x} ${a.y} Q ${midX} ${midY} ${b.x} ${b.y}"></path>`;
    }).join("");
    const activeNodeId = state.currentWikiNodeId || layout.centerId;
    const nodeHtml = layout.nodes.map((node) => `
      <button
        class="graph-node ${node.type} ${node.size || "medium"} ${node.id === activeNodeId ? "active" : ""}"
        data-node-id="${escapeHtml(graphId(node))}"
        data-real-node-id="${escapeHtml(node.real_node_id || "")}"
        data-node-title="${escapeHtml(graphTitle(node))}"
        data-node-body="${escapeHtml(graphBody(node))}"
        title="${escapeHtml(graphTitle(node))}"
        style="left:${node.x}%;top:${node.y}%"
        type="button"
      >
        <span class="node-dot"></span>
        <span class="node-label">${escapeHtml(graphTitle(node))}</span>
      </button>
    `).join("");
    const graphNote = hasBackendGraph
      ? `知识库架构 · ${layout.sourceCount} 原始节点 / ${layout.sourceEdgeCount} 原始关系 → ${layout.nodes.length} 展示节点`
      : state.wikiNodes.length
        ? `当前检索结果 · ${layout.sourceCount} 原始节点 → ${layout.nodes.length} 展示节点`
        : "本地预览数据";
    target.innerHTML = `
      <div class="graph-canvas">
        <svg class="graph-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${lineHtml}</svg>
        <div class="graph-legend">
          <span><i class="legend-dot topic"></i>概念</span>
          <span><i class="legend-dot method"></i>方法</span>
          <span><i class="legend-dot paper"></i>论文/报告</span>
          <span><i class="legend-dot frontier"></i>画像/前沿</span>
        </div>
        <div class="graph-tools" aria-label="图谱工具">
          <button data-graph-action="zoom-in" type="button" title="放大">＋</button>
          <button data-graph-action="zoom-out" type="button" title="缩小">－</button>
          <button data-graph-action="focus" type="button" title="聚焦中心">⌖</button>
        </div>
        ${nodeHtml}
      </div>
      <div class="graph-note">${graphNote}</div>
    `;
  }

  function renderWikiList() {
    const nodes = state.wikiNodes.length ? state.wikiNodes : state.wikiGraph?.nodes?.length ? state.wikiGraph.nodes : DEMO_MODE ? demoWikiNodes : [];
    if (!nodes.length) {
      $("wikiGraph").innerHTML = `
        <div class="wiki-empty-state">
          <strong>暂无 Wiki 条目</strong>
          <p>生成精读报告或提交反馈后，这里会展示本地 Wiki 条目。</p>
        </div>
      `;
      return;
    }
    $("wikiGraph").innerHTML = `
      <div class="wiki-list-view">
        ${nodes.map((node) => `
          <button class="result-item" data-node-id="${escapeHtml(graphId(node))}" data-node-title="${escapeHtml(graphTitle(node))}" data-node-body="${escapeHtml(graphBody(node))}" type="button">
            <h3>${escapeHtml(graphTitle(node))} <span class="status-chip">${escapeHtml(node.node_type || node.type || "node")}</span></h3>
            <p>${escapeHtml(graphBody(node) || "暂无摘要。")}</p>
          </button>
        `).join("")}
      </div>
    `;
  }

  function graphNodesById() {
    const nodes = uniqueGraphNodes([
      ...(state.wikiMap?.nodes || []),
      ...(state.wikiGraph?.nodes || []),
      ...(state.wikiNodes || [])
    ]);
    return Object.fromEntries(nodes.map((node) => [graphId(node), node]));
  }

  function currentGraphEdges() {
    return (state.wikiGraph?.edges || []).map(normalizeGraphEdge);
  }

  function relationLabel(raw) {
    return String(raw || "related").replaceAll("_", " ");
  }

  function pickWikiFocusNodeId() {
    const nodes = state.wikiGraph?.nodes || [];
    if (!nodes.length) return "";
    const edges = currentGraphEdges();
    const degree = graphDegreeMap(nodes, edges);
    const candidates = nodes.filter((node) => {
      const id = graphId(node);
      const type = graphType(node);
      return !id.startsWith("user:") && type !== "frontier";
    });
    return (candidates.length ? candidates : nodes).reduce((best, node) => {
      const id = graphId(node);
      const typeBoost = graphType(node) === "topic" ? 1.2 : graphType(node) === "paper" ? 0.7 : 0.4;
      const score = (degree[id] || 0) + Number(node.score || 0) + typeBoost;
      const bestNode = nodes.find((item) => graphId(item) === best);
      const bestTypeBoost = bestNode && graphType(bestNode) === "topic" ? 1.2 : bestNode && graphType(bestNode) === "paper" ? 0.7 : 0.4;
      const bestScore = (degree[best] || 0) + Number(bestNode?.score || 0) + bestTypeBoost;
      return score > bestScore ? id : best;
    }, graphId(candidates[0] || nodes[0]));
  }

  function relatedWikiNodes(nodeId) {
    const byId = graphNodesById();
    return currentGraphEdges()
      .filter((edge) => edge.src_id === nodeId || edge.dst_id === nodeId)
      .map((edge) => {
        const neighborId = edge.src_id === nodeId ? edge.dst_id : edge.src_id;
        const node = byId[neighborId];
        return node ? { node, edge, neighborId } : null;
      })
      .filter(Boolean)
      .sort((a, b) => graphWeight(b.edge) - graphWeight(a.edge));
  }

  function renderWikiTags(items = []) {
    const tags = Array.from(new Set(items.map((item) => String(item || "").trim()).filter(Boolean))).slice(0, 8);
    $("wikiTags").innerHTML = tags.length
      ? tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
      : "<span>本地 Wiki</span><span>用户画像</span><span>精读报告</span>";
  }

  function renderWikiResultNodes(nodes, summary = "") {
    const target = $("wikiResults");
    if (!nodes.length) {
      target.className = "result-list empty";
      target.textContent = "没有匹配的知识节点。";
      $("wikiEvidenceSummary").textContent = summary || "0 条";
      renderWikiTags([]);
      return;
    }
    target.className = "result-list";
    target.innerHTML = nodes.map((node) => `
      <button class="result-item" data-node-id="${escapeHtml(node.node_id || graphId(node))}" data-node-title="${escapeHtml(node.title || graphTitle(node))}" data-node-body="${escapeHtml(node.body || node.snippet || "")}" type="button">
        <h3>${escapeHtml(node.title || graphTitle(node))} <span class="status-chip">${escapeHtml(node.node_type || graphTypeLabel(node))}</span></h3>
        <p>${escapeHtml(node.body || node.snippet || "暂无摘要。")}</p>
        <div class="evidence-meta">${wikiEvidenceMeta(node).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </button>
    `).join("");
    $("wikiEvidenceSummary").textContent = summary || `${nodes.length} 条`;
    renderWikiTags(nodes.flatMap((node) => [node.node_type, ...(String(node.keywords || "").split(/[,\s]+/))]));
  }

  function renderWikiRelations(nodeId) {
    const current = graphNodesById()[nodeId];
    const semanticPapers = current?.related_papers || [];
    const allRelated = semanticPapers.length
      ? semanticPapers.map((node) => ({ node, edge: { relation: "关联论文", weight: Number(node.score || 1) || 1 } }))
      : nodeId ? relatedWikiNodes(nodeId) : [];
    const paperRelated = allRelated.filter(({ node }) => graphType(node) === "paper");
    const related = [
      ...paperRelated,
      ...allRelated.filter(({ node }) => graphType(node) !== "paper")
    ].slice(0, 4);
    if (!related.length) {
      const fallbackNodes = state.wikiGraph?.nodes?.length ? state.wikiGraph.nodes.slice(0, 10) : state.wikiNodes.slice(0, 10);
      renderWikiResultNodes(fallbackNodes.filter((node) => graphId(node) !== nodeId), fallbackNodes.length ? "图谱节点" : "0 条");
      return;
    }

    $("wikiResults").className = "result-list";
    $("wikiResults").innerHTML = related.map(({ node, edge }) => `
      <button class="result-item relationship-row" data-node-id="${escapeHtml(graphId(node))}" data-node-title="${escapeHtml(graphTitle(node))}" data-node-body="${escapeHtml(graphBody(node))}" type="button">
        <h3>${escapeHtml(graphTitle(node))} <span class="status-chip">${escapeHtml(graphTypeLabel(node))}</span></h3>
        <p>${escapeHtml(graphBody(node) || "暂无摘要。")}</p>
        <div class="evidence-meta">
          <span>${escapeHtml(relationLabel(edge.relation))}</span>
          <span>${Math.round(graphWeight(edge) * 100)}%</span>
          ${node.file_path ? `<span>${escapeHtml(node.file_path)}</span>` : ""}
        </div>
      </button>
    `).join("");
    $("wikiEvidenceSummary").textContent = `${related.length} 条关系`;
    renderWikiTags([
      current ? graphTypeLabel(current) : "",
      ...(String(current?.keywords || "").split(/[,\s]+/)),
      ...related.map(({ edge }) => relationLabel(edge.relation)),
      ...related.map(({ node }) => graphTypeLabel(node))
    ]);
  }

  function renderWikiEntryHtml(body) {
    const content = String(body || "").trim();
    if (!content) return "<p>暂无摘要。</p>";
    if (/^#{1,3}\s|\n#{1,3}\s|\n-\s/.test(content)) {
      return renderMarkdown(content);
    }
    return content
      .split(/\n{2,}/)
      .map((paragraph) => `<p>${escapeHtml(paragraph.trim())}</p>`)
      .join("");
  }

  function setWikiEntry(title, body, nodeId = "", options = {}) {
    const editor = $("wikiEntryEditor");
    const display = $("wikiEntryBody");
    const editButton = $("editWikiEntryBtn");
    state.currentWikiNodeId = nodeId || "";
    state.currentWikiEditNodeId = options.editNodeId || (String(nodeId || "").startsWith("architecture:") ? "" : nodeId || "");
    $("wikiEntryTitle").textContent = title || "知识库架构";
    display.dataset.rawBody = body || "";
    display.innerHTML = renderWikiEntryHtml(body);
    display.hidden = false;
    editor.hidden = true;
    editButton.disabled = !state.currentWikiEditNodeId;
    editButton.textContent = state.currentWikiEditNodeId ? "编辑" : "架构节点";
    if (options.renderRelations !== false) {
      renderWikiRelations(state.currentWikiNodeId);
      if (state.wikiView === "graph") renderWikiGraph();
    }
  }

  function setWikiView(view) {
    state.wikiView = view;
    document.querySelectorAll("[data-wiki-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.wikiView === view);
    });
    if (view === "list") {
      renderWikiList();
    } else {
      renderWikiGraph();
    }
  }

  function wikiEvidenceMeta(node) {
    const type = node.node_type || node.type || "node";
    const score = node.score !== undefined ? `${normalizeScore(node.score)}%` : "";
    const source = node.source || node.paper_title || node.file_path || "";
    return [type, score, source].filter(Boolean).slice(0, 3);
  }

  function setWikiMapFocus(nodeId = "architecture:core") {
    const focus = state.wikiMap?.byId?.[nodeId] || state.wikiMap?.nodes?.[0];
    if (!focus) {
      setWikiEntry("知识库架构", "暂无可展示的用户知识节点。", "", { renderRelations: false });
      renderWikiResultNodes([], "0 条");
      return;
    }
    setWikiEntry(graphTitle(focus), graphBody(focus), graphId(focus), { editNodeId: focus.real_node_id || "" });
  }

  async function loadWiki() {
    const stats = await api(`/api/wiki/stats?user_id=${encodeURIComponent(currentUser())}`);
    $("wikiNodeStat").textContent = stats.nodes || 0;
    $("wikiSettingStat").textContent = stats.nodes || "-";
    $("wikiStats").textContent = `节点 ${stats.nodes || 0} · 关系 ${stats.edges || 0} · 引用 ${stats.citations || 0}`;
    try {
      state.wikiGraph = await api(`/api/wiki/graph?user_id=${encodeURIComponent(currentUser())}&limit=48`);
    } catch (error) {
      console.warn("Wiki graph unavailable, falling back to search nodes.", error);
      state.wikiGraph = null;
    }
    state.wikiNodes = state.wikiGraph?.nodes || [];
    if (!state.wikiNodes.length && Number(stats.nodes || 0) > 0) {
      const fallback = await api(`/api/wiki/search?user_id=${encodeURIComponent(currentUser())}&limit=48`);
      state.wikiNodes = fallback.nodes || [];
      if (state.wikiNodes.length) {
        state.wikiGraph = {
          ok: true,
          nodes: state.wikiNodes,
          edges: state.wikiGraph?.edges || [],
          source: "wiki_search_fallback",
          query: ""
        };
        $("wikiStats").textContent = `节点 ${stats.nodes || 0} · 关系 ${stats.edges || 0} · 引用 ${stats.citations || 0} · 已用节点列表恢复`;
      }
    }
    if (state.wikiView === "graph") {
      renderWikiGraph();
      setWikiMapFocus("architecture:core");
    } else {
      const focusId = pickWikiFocusNodeId();
      const focusNode = graphNodesById()[focusId];
      if (focusNode) {
        setWikiEntry(graphTitle(focusNode), graphBody(focusNode), graphId(focusNode));
      } else {
        setWikiEntry("知识库架构", "暂无可展示的用户知识节点。", "", { renderRelations: false });
        renderWikiResultNodes([], "0 条");
      }
      renderWikiList();
    }
  }

  async function searchWiki() {
    const rawQuery = $("wikiQuery").value.trim();
    if (!rawQuery) {
      await loadWiki();
      return;
    }
    const data = await api(`/api/wiki/search?user_id=${encodeURIComponent(currentUser())}&q=${encodeURIComponent(rawQuery)}&limit=20`);
    const nodes = data.nodes || [];
    state.wikiNodes = nodes;
    try {
      const graph = await api(`/api/wiki/graph?user_id=${encodeURIComponent(currentUser())}&q=${encodeURIComponent(rawQuery)}&limit=48`);
      if (graph.nodes?.length) state.wikiGraph = graph;
    } catch (error) {
      console.warn("Wiki search graph unavailable.", error);
    }
    renderWikiResultNodes(nodes, `${nodes.length} 条结果`);
    if (nodes[0]) setWikiEntry(nodes[0].title || graphTitle(nodes[0]), nodes[0].body || nodes[0].snippet || "", nodes[0].node_id || graphId(nodes[0]), { renderRelations: false });
    if (state.wikiView === "graph") renderWikiGraph();
    if (state.wikiView === "list") renderWikiList();
  }

  function normalizeCitationSource(source, index = 0) {
    const metadata = source?.metadata || {};
    const citationIndex = Number(source?.index || index + 1);
    const nodeType = source?.node_type || source?.type || "";
    const sourceType = source?.source_type || "";
    const sourceId = source?.source_id || "";
    const meta = source?.meta || [sourceType, sourceId].filter(Boolean).join(" · ") || "参考文献";
    const title = String(source?.title || source?.node_id || `参考文献 ${citationIndex}`).replace(/^Wiki:\s*/i, "").replace(/^Q\d+[\s:-]*/i, "");
    return {
      index: citationIndex,
      node_id: source?.node_id || source?.id || "",
      node_type: nodeType,
      title,
      meta,
      snippet: source?.snippet || source?.excerpt || source?.body || "",
      source_type: sourceType,
      source_id: sourceId,
      anchor: source?.anchor || "",
      url: source?.url || metadata.url || metadata.abs_url || metadata.pdf_url || "",
      metadata
    };
  }

  function normalizeCitations(data) {
    const raw = Array.isArray(data?.citations) && data.citations.length ? data.citations : data?.sources;
    const items = Array.isArray(raw) ? raw : DEMO_MODE ? demoSources : [];
    return items.map((source, index) => normalizeCitationSource(source, index));
  }

  function renderAnswerWithCitations(text, citations = []) {
    const refs = new Map(citations.map((citation) => [String(citation.index), citation]));
    const escaped = escapeHtml(text || "");
    if (!escaped) return "<p>正在生成回答...</p>";
    const linked = escaped.replace(/\[(\d{1,3})\]/g, (match, index) => {
      if (!refs.has(String(index))) return match;
      const citation = refs.get(String(index));
      return `<button type="button" class="citation-ref" data-citation-index="${index}" title="${escapeHtml(citation.title)}">[${index}]</button>`;
    });
    return linked
      .split(/\n{2,}/)
      .map((block) => `<p>${block.replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  function routingLabel(reason) {
    return {
      explicit_mention: "@ 指定来源",
      local_research_context: "本地证据",
      scope_recent: "最近 7 天",
      scope_profile: "当前方向",
      general_question: "通用问题",
      no_local_context_signal: "直接回答"
    }[reason] || reason || "";
  }

  function renderAnswerMeta(data = {}, citations = []) {
    const wikiMode = data.retrieval_required !== false && data.mode !== "direct";
    const modeText = wikiMode ? `参考文献 · ${citations.length} 条` : "直接回答";
    const route = wikiMode ? "" : routingLabel(data.routing_reason);
    return `
      <div class="answer-meta">
        <span class="${wikiMode ? "wiki" : "direct"}">${escapeHtml(modeText)}</span>
        ${route ? `<span>${escapeHtml(route)}</span>` : ""}
        <span>流式输出</span>
      </div>
    `;
  }

  function renderChatSources(sources = DEMO_MODE ? demoSources : []) {
    const items = Array.isArray(sources) ? sources.map((source, index) => normalizeCitationSource(source, index)) : [];
    $("chatSources").className = items.length ? "source-list" : "source-list empty";
    $("chatSources").innerHTML = items.length ? items.map((source) => {
      const openControl = source.url
        ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">打开原文</a>`
        : `<button type="button" data-open-citation-source data-node-id="${escapeHtml(source.node_id)}" data-title="${escapeHtml(source.title)}">查看来源</button>`;
      return `
        <div class="source-card citation-card" tabindex="0" data-citation-index="${escapeHtml(source.index)}" data-node-id="${escapeHtml(source.node_id)}" data-title="${escapeHtml(source.title)}">
          <h3>[${escapeHtml(source.index)}] ${escapeHtml(source.title)}</h3>
          <p>${escapeHtml(source.meta)}</p>
          ${source.snippet ? `<p>${escapeHtml(source.snippet)}</p>` : ""}
          ${openControl}
        </div>
      `;
    }).join("") : "暂无参考文献。";
  }

  function focusCitationSource(index) {
    const card = document.querySelector(`#chatSources [data-citation-index="${CSS.escape(String(index))}"]`);
    if (!card) return;
    document.querySelectorAll("#chatSources .source-card.active").forEach((item) => item.classList.remove("active"));
    card.classList.add("active");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    window.setTimeout(() => card.classList.remove("active"), 2600);
  }

  async function openCitationSource(nodeId, title) {
    setView("wiki", true, { skipLoad: true });
    $("wikiQuery").value = title || nodeId || "";
    await searchWiki();
  }

  function chunkText(text) {
    const content = String(text || "");
    if (!content) return [""];
    const chunks = [];
    for (let index = 0; index < content.length; index += 12) {
      chunks.push(content.slice(index, index + 12));
    }
    return chunks;
  }

  async function streamAnswerText(target, text, citations) {
    target.classList.remove("loading");
    let partial = "";
    for (const chunk of chunkText(text)) {
      partial += chunk;
      target.innerHTML = renderAnswerWithCitations(partial, citations);
      $("chatThread").scrollTop = $("chatThread").scrollHeight;
      await new Promise((resolve) => window.setTimeout(resolve, 12));
    }
  }

  function parseSseFrame(frame) {
    const lines = frame.split(/\r?\n/);
    let event = "message";
    const dataLines = [];
    lines.forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    });
    if (!dataLines.length) return null;
    return { event, data: JSON.parse(dataLines.join("\n")) };
  }

  async function streamWikiAsk(payload, answerTarget, message) {
    const response = await fetch("/api/wiki/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok || !response.body) throw new Error("流式问答接口不可用");

    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = "";
    let text = "";
    let result = {};
    let citations = [];

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\n\n/);
      buffer = frames.pop() || "";
      for (const frame of frames) {
        if (!frame.trim()) continue;
        const parsed = parseSseFrame(frame);
        if (!parsed) continue;
        if (parsed.event === "error") throw new Error(parsed.data.error || "流式问答失败");
        if (parsed.event === "status") {
          answerTarget.innerHTML = `<p>${escapeHtml(parsed.data.text || "正在生成回答")}</p>`;
        }
        if (parsed.event === "meta") {
          result = { ...result, ...parsed.data };
          citations = normalizeCitations(parsed.data);
          const metaTarget = message.querySelector(".answer-meta");
          if (metaTarget) metaTarget.outerHTML = renderAnswerMeta(parsed.data, citations);
          renderChatSources(citations);
        }
        if (parsed.event === "chunk") {
          text += parsed.data.text || "";
          answerTarget.classList.remove("loading");
          answerTarget.innerHTML = renderAnswerWithCitations(text, citations);
          $("chatThread").scrollTop = $("chatThread").scrollHeight;
        }
        if (parsed.event === "done") {
          result = { ...result, ...parsed.data };
          text = parsed.data.text || text;
          citations = normalizeCitations(parsed.data);
          const metaTarget = message.querySelector(".answer-meta");
          if (metaTarget) metaTarget.outerHTML = renderAnswerMeta(parsed.data, citations);
          answerTarget.classList.remove("loading");
          answerTarget.innerHTML = renderAnswerWithCitations(text, citations);
          renderChatSources(citations);
        }
      }
    }
    return { ...result, text, citations };
  }

  function mentionQueryAtCursor() {
    const input = $("chatInput");
    const cursor = input.selectionStart ?? input.value.length;
    const before = input.value.slice(0, cursor);
    const match = before.match(/@([^\s@\]\)（），。；;、,]*)$/);
    if (!match) return null;
    return {
      query: match[1] || "",
      start: cursor - match[0].length,
      end: cursor
    };
  }

  function renderChatMentionChips() {
    const target = $("chatMentionChips");
    const mentions = state.chatMentions || [];
    target.hidden = !mentions.length;
    target.innerHTML = mentions.map((mention) => `
      <span class="mention-chip" data-node-id="${escapeHtml(mention.node_id)}">
        @${escapeHtml(mention.title)}
        <button type="button" data-remove-mention="${escapeHtml(mention.node_id)}" aria-label="移除 ${escapeHtml(mention.title)}">×</button>
      </span>
    `).join("");
  }

  function renderMentionSuggestions(nodes = []) {
    const panel = $("mentionSuggestions");
    const items = Array.isArray(nodes) ? nodes.slice(0, 6) : [];
    panel.hidden = !items.length;
    panel.innerHTML = items.map((node) => {
      const nodeId = node.node_id || node.id || node.title || "";
      const title = node.title || nodeId || "未命名节点";
      const meta = [node.node_type || node.type || "Wiki", node.score ? `匹配 ${Math.round(Number(node.score) * 100)}%` : ""].filter(Boolean).join(" · ");
      const body = node.body || node.snippet || "";
      return `
        <button type="button" data-mention-node-id="${escapeHtml(nodeId)}" data-title="${escapeHtml(title)}" data-node-type="${escapeHtml(node.node_type || node.type || "")}">
          <strong>@${escapeHtml(title)}</strong>
          <span>${escapeHtml(meta)}${body ? ` · ${escapeHtml(String(body).slice(0, 70))}` : ""}</span>
        </button>
      `;
    }).join("");
  }

  async function searchMentionSuggestions() {
    const context = mentionQueryAtCursor();
    if (!context) {
      $("mentionSuggestions").hidden = true;
      return;
    }
    const token = ++state.mentionSearchToken;
    const data = await api(`/api/wiki/search?user_id=${encodeURIComponent(currentUser())}&q=${encodeURIComponent(context.query)}&limit=6`);
    if (token !== state.mentionSearchToken) return;
    renderMentionSuggestions(data.nodes || []);
  }

  function scheduleMentionSearch() {
    window.clearTimeout(state.mentionSearchTimer);
    state.mentionSearchTimer = window.setTimeout(() => {
      searchMentionSuggestions().catch((error) => console.warn("Mention search failed.", error));
    }, 160);
  }

  function insertMention(node) {
    const input = $("chatInput");
    const context = mentionQueryAtCursor();
    const title = node.title || node.node_id || "Wiki";
    const nodeId = node.node_id || node.id || title;
    const mentionText = `@[${title}](${nodeId})`;
    const start = context?.start ?? input.selectionStart ?? input.value.length;
    const end = context?.end ?? input.selectionEnd ?? input.value.length;
    input.value = `${input.value.slice(0, start)}${mentionText} ${input.value.slice(end)}`;
    const cursor = start + mentionText.length + 1;
    input.setSelectionRange(cursor, cursor);
    if (!state.chatMentions.some((mention) => mention.node_id === nodeId)) {
      state.chatMentions.push({
        node_id: nodeId,
        title,
        node_type: node.node_type || node.type || ""
      });
    }
    renderChatMentionChips();
    window.clearTimeout(state.mentionSearchTimer);
    state.mentionSearchToken += 1;
    $("mentionSuggestions").hidden = true;
    input.focus();
  }

  function activeMentionsForQuestion(question) {
    const selected = state.chatMentions.filter((mention) => {
      const nodeId = mention.node_id || "";
      const title = mention.title || "";
      return (nodeId && question.includes(nodeId)) || (title && question.includes(title));
    });
    return selected.map((mention) => ({
      node_id: mention.node_id,
      title: mention.title,
      node_type: mention.node_type
    }));
  }

  function clearChatMentions() {
    state.chatMentions = [];
    renderChatMentionChips();
  }

  async function askWiki() {
    const input = $("chatInput");
    const button = $("wikiAskBtn");
    const question = input.value.trim();
    if (!question) return;
    const payload = {
      user_id: currentUser(),
      question,
      scope: document.querySelector("input[name='chatScope']:checked")?.value || "all",
      limit: 8,
      mentions: activeMentionsForQuestion(question)
    };
    $("chatThread").insertAdjacentHTML("beforeend", `
      <div class="message user">
        <div class="avatar">我</div>
        <div class="bubble"><p>${escapeHtml(question)}</p></div>
      </div>
    `);
    input.value = "";
    clearChatMentions();
    window.clearTimeout(state.mentionSearchTimer);
    state.mentionSearchToken += 1;
    $("mentionSuggestions").hidden = true;

    const messageId = `assistant-${Date.now()}`;
    $("chatThread").insertAdjacentHTML("beforeend", `
      <div class="message assistant" id="${messageId}">
        <div class="avatar">AI</div>
        <div class="bubble">
          <div class="answer-meta"><span>准备回答</span></div>
          <div class="answer-text loading"><p>正在生成回答...</p></div>
        </div>
      </div>
    `);
    const message = $(messageId);
    const metaTarget = message.querySelector(".answer-meta");
    const answerTarget = message.querySelector(".answer-text");
    const previousText = button.textContent;
    button.disabled = true;
    button.textContent = "生成中";

    try {
      let data;
      if (DEMO_MODE) {
        data = await api("/api/wiki/ask", { method: "POST", body: JSON.stringify(payload) });
        const citations = normalizeCitations(data);
        metaTarget.outerHTML = renderAnswerMeta(data, citations);
        await streamAnswerText(answerTarget, data.text || "", citations);
        renderChatSources(citations);
      } else {
        try {
          data = await streamWikiAsk(payload, answerTarget, message);
        } catch (streamError) {
          console.warn("Streaming Wiki ask failed, falling back to JSON.", streamError);
          data = await api("/api/wiki/ask", { method: "POST", body: JSON.stringify(payload) });
          const citations = normalizeCitations(data);
          const currentMeta = message.querySelector(".answer-meta");
          if (currentMeta) currentMeta.outerHTML = renderAnswerMeta(data, citations);
          await streamAnswerText(answerTarget, data.text || "", citations);
          renderChatSources(citations);
        }
        const citations = normalizeCitations(data);
      }
      $("chatThread").scrollTop = $("chatThread").scrollHeight;
    } catch (error) {
      answerTarget.classList.remove("loading");
      answerTarget.innerHTML = `<p>生成失败：${escapeHtml(error.message || String(error))}</p>`;
      throw error;
    } finally {
      button.disabled = false;
      button.textContent = previousText;
    }
  }

  function envMap(data) {
    const entries = data.editable_env || data.env || {};
    if (Array.isArray(entries)) {
      return Object.fromEntries(entries.filter((item) => item?.key).map((item) => [item.key, item]));
    }
    return Object.fromEntries(Object.entries(entries).map(([key, value]) => [
      key,
      typeof value === "object" && value !== null ? value : { key, value, is_secret: false, present: true }
    ]));
  }

  function envInfo(env, key, fallback = "", aliases = []) {
    const candidates = [key, ...aliases];
    const actualKey = candidates.find((candidate) => {
      const item = env[candidate];
      return item && (item.present || item.value);
    }) || candidates.find((candidate) => env[candidate]);
    const item = env[actualKey] || { key, value: fallback, is_secret: false, present: Boolean(fallback) };
    const value = item.value || fallback || "";
    return {
      key: actualKey || key,
      value,
      isSecret: Boolean(item.is_secret || item.masked),
      present: Boolean(item.present || value || fallback)
    };
  }

  function setEnvFieldValue(id, env, key, fallback = "", aliases = []) {
    const input = $(id);
    if (!input) return null;
    const info = envInfo(env, key, fallback, aliases);
    input.dataset.envKey = info.key;
    input.value = info.isSecret && info.present ? "***" : info.value;
    return info;
  }

  function setSourceStatus(id, configuredText, missingText, configured) {
    const target = $(id);
    if (!target) return;
    target.textContent = configured ? configuredText : missingText;
    target.classList.toggle("configured", Boolean(configured));
  }

  function setConferenceAccessMode(mode) {
    const normalized = ["public", "credential", "manual"].includes(mode) ? mode : "public";
    document.querySelectorAll('input[name="conferenceAccessMode"]').forEach((input) => {
      input.checked = input.value === normalized;
    });
  }

  function currentConferenceAccessMode() {
    return document.querySelector('input[name="conferenceAccessMode"]:checked')?.value || "public";
  }

  function syncConferenceAccessUi(mode = currentConferenceAccessMode(), hasConferenceAuth = false) {
    const normalized = ["public", "credential", "manual"].includes(mode) ? mode : "public";
    const panel = document.querySelector(".source-auth-panel");
    if (panel) panel.dataset.mode = normalized;

    document.querySelectorAll(".source-auth-fields input").forEach((input) => {
      input.disabled = normalized !== "credential";
    });

    if (normalized === "manual" && $("settingEnableCustomRss")) {
      $("settingEnableCustomRss").checked = true;
    }

    if ($("conferenceAuthStatus")) {
      $("conferenceAuthStatus").textContent = normalized === "credential"
        ? hasConferenceAuth ? "本地授权已配置" : "等待授权配置"
        : normalized === "manual" ? "手动补充优先" : "公开源优先";
    }
  }

  function updateSourceAuthStatus(sourcePrefs, env) {
    const semanticKey = envInfo(env, "SEMANTIC_SCHOLAR_API_KEY");
    const openReviewUser = envInfo(env, "OPENREVIEW_USERNAME");
    const openReviewToken = envInfo(env, "OPENREVIEW_TOKEN");
    const openReviewCookie = envInfo(env, "OPENREVIEW_COOKIE_FILE");
    const conferenceCookie = envInfo(env, "PAPERFLOW_CONFERENCE_COOKIE_FILE");
    const hasOpenReviewAuth = openReviewUser.present || openReviewToken.present || openReviewCookie.present;
    const hasConferenceAuth = hasOpenReviewAuth || conferenceCookie.present;
    const mode = currentConferenceAccessMode() || sourcePrefs.conference_access_mode || "public";

    setSourceStatus("semanticScholarAuthStatus", "API Key 已配置", "API Key 可选", semanticKey.present);
    setSourceStatus("openReviewAuthStatus", "本地授权已配置", "公开优先", hasOpenReviewAuth);
    syncConferenceAccessUi(mode, hasConferenceAuth);
  }

  function envRow(env, key, label, fallback = "", aliases = []) {
    const info = envInfo(env, key, fallback, aliases);
    const type = info.isSecret ? "password" : "text";
    const value = info.isSecret && !info.value && info.present ? "***" : info.value;
    const wide = info.key.includes("BASE_URL") ? " wide-env" : "";
    return `
      <div class="env-row${wide}">
        <label for="env_${escapeHtml(info.key)}">${escapeHtml(label)}</label>
        <input id="env_${escapeHtml(info.key)}" data-env-key="${escapeHtml(info.key)}" value="${escapeHtml(value)}" type="${type}" placeholder="${info.present ? "" : "未配置"}">
      </div>
    `;
  }

  function boolValue(value) {
    return value === true || ["1", "true", "yes", "on"].includes(String(value).toLowerCase());
  }

  function splitListValue(value) {
    if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
    return String(value || "").split(/[,;\n]/).map((item) => item.trim()).filter(Boolean);
  }

  function renderSettingTags(id, values) {
    const target = $(id);
    if (!target) return;
    const items = splitListValue(values);
    target.innerHTML = items.length
      ? items.map((item) => `<span>${escapeHtml(item)}</span>`).join("")
      : `<span>未配置</span>`;
  }

  function selectedUserInfo(userId = currentUser()) {
    return state.users.find((user) => user.user_id === userId) || normalizeUser(userId);
  }

  function firstText(...values) {
    for (const value of values) {
      if (Array.isArray(value)) {
        const joined = splitListValue(value).join("; ");
        if (joined) return joined;
      } else if (value && typeof value === "object") {
        const text = value.url || value.href || value.path || value.value || "";
        if (String(text).trim()) return String(text).trim();
      } else if (String(value || "").trim()) {
        return String(value).trim();
      }
    }
    return "";
  }

  function pairLabel(item) {
    if (Array.isArray(item)) return String(item[0] || "").trim();
    if (item && typeof item === "object") return String(item.label || item.name || item.key || item.title || "").trim();
    return String(item || "").trim();
  }

  function sortedProfilePairs(profile, raw, summaryKey, rawKey) {
    const summaryItems = Array.isArray(profile?.[summaryKey]) ? profile[summaryKey] : [];
    if (summaryItems.length) return summaryItems.map(pairLabel).filter(Boolean);
    return Object.entries(raw?.[rawKey] || profile?.[rawKey] || {})
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .map(([key]) => key)
      .filter(Boolean);
  }

  function profileMustReadValues(profile, raw) {
    const mustRead = raw?.must_read || profile?.must_read || {};
    return {
      authors: splitListValue(mustRead.authors || []),
      institutions: splitListValue(mustRead.institutions || []),
      keywords: splitListValue(mustRead.keywords || [])
    };
  }

  function listText(items, limit = 8) {
    const values = splitListValue(items).slice(0, limit);
    return values.length ? values.join("、") : "未记录";
  }

  function profileEditableDescription(raw, userInfo) {
    return firstText(
      raw?.description,
      raw?.natural_language,
      raw?.research_description,
      raw?.summary,
      userInfo?.description
    );
  }

  function profileAffiliation(raw, userInfo) {
    return firstText(
      raw?.affiliation,
      raw?.affiliations,
      raw?.organization,
      raw?.organizations,
      raw?.institution,
      raw?.user_info?.affiliation,
      raw?.user_info?.organization,
      raw?.metadata?.affiliation,
      raw?.metadata?.organization,
      userInfo?.affiliation
    );
  }

  function profileInfoItem(label, value, variant = "") {
    const normalized = firstText(value) || "未记录";
    const emptyClass = normalized === "未记录" ? " empty" : "";
    const variantClass = variant ? ` ${variant}` : "";
    return `<div class="profile-info-item${variantClass}${emptyClass}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(normalized)}</strong></div>`;
  }

  function renderProfileInfoGrid(profile, raw, userInfo, details) {
    const target = $("profileInfoGrid");
    if (!target) return;
    const mustRead = profileMustReadValues(profile, raw);
    const drift = profile?.drift_state || raw?.drift_state || {};
    const updatedAt = firstText(profile?.updated_at, raw?.updated_at, userInfo?.updated_at);
    target.innerHTML = [
      profileInfoItem("用户", details.userId),
      profileInfoItem("角色", userInfo?.role_name || userInfo?.label || ""),
      profileInfoItem("版本", firstText(profile?.version, raw?.version)),
      profileInfoItem("更新时间", updatedAt),
      profileInfoItem("所属机构", profileAffiliation(raw, userInfo), "wide"),
      profileInfoItem("方向", listText(details.directions, 8), "wide"),
      profileInfoItem("关键词", listText(mustRead.keywords, 10), "wide"),
      profileInfoItem("作者", listText(mustRead.authors, 8), "wide"),
      profileInfoItem("关注机构", listText(mustRead.institutions, 8), "wide"),
      profileInfoItem("主题", listText(details.topics, 10), "wide"),
      profileInfoItem("漂移状态", firstText(drift.status, raw?.drift_status), "wide")
    ].join("");
  }

  function setProfileSyncStatus(message) {
    const target = $("profileSyncStatus");
    if (target) target.textContent = message;
  }

  function renderProfileForm(data = {}) {
    const profile = data.profile || {};
    const raw = data.raw || {};
    const userId = firstText(raw.user_id, profile.user_id, currentUser()) || "user_demo";
    const userInfo = selectedUserInfo(userId);
    const directions = sortedProfilePairs(profile, raw, "top_directions", "core_directions");
    const topics = sortedProfilePairs(profile, raw, "top_topics", "topic_weights");

    state.currentProfile = { profile, raw };
    $("profileUserId").value = userId;
    $("scholarUrl").value = firstText(raw.scholar_url, raw.scholar_profile?.url, raw.source_inputs?.scholar_url);
    $("homepageUrl").value = firstText(raw.homepage_url, raw.homepage_profile?.url, raw.source_inputs?.homepage_url);
    $("pdfPaths").value = firstText(raw.pdf_paths, raw.source_pdfs, raw.source_inputs?.pdf_paths);
    renderProfileInfoGrid(profile, raw, userInfo, { userId, directions, topics });
    $("naturalLanguage").value = profileEditableDescription(raw, userInfo);
    $("resetProfile").checked = false;

    const updatedAt = firstText(profile.updated_at, raw.updated_at, userInfo.updated_at);
    setProfileSyncStatus(updatedAt ? `画像已加载 · ${updatedAt}` : (userInfo.has_profile ? "画像已加载" : "尚未生成画像，可在此补充"));
  }

  async function loadCurrentProfile() {
    const userId = currentUser();
    if (!userId) return;
    const token = ++state.profileLoadToken;
    setProfileSyncStatus("正在加载画像...");
    const data = await api(`/api/profile?user_id=${encodeURIComponent(userId)}`);
    if (token !== state.profileLoadToken) return;
    renderProfileForm(data);
  }

  function conferenceAccessInfo(item) {
    const source = String(item.source || item.label || item.id || "").toLowerCase();
    if (source.includes("openreview")) {
      return {
        method: "OpenReview",
        auth: "公开/可选登录",
        detail: "公开论文可抓取；review、discussion 或补充材料可能需要本地授权。",
        priority: "高"
      };
    }
    if (source.includes("aclanthology") || source.includes("anthology")) {
      return {
        method: "ACL Anthology",
        auth: "公开",
        detail: "论文元数据和 PDF 通常公开，适合直接作为会议源。",
        priority: "高"
      };
    }
    if (source.includes("cvf") || source.includes("ecva")) {
      return {
        method: source.includes("ecva") ? "ECVA" : "CVF Open Access",
        auth: "公开",
        detail: "公开论文页面优先；poster/session 信息可通过 RSS 或会议页面补充。",
        priority: "中"
      };
    }
    if (source.includes("dblp") || source.includes("acm")) {
      return {
        method: source.includes("acm") ? "ACM / DBLP" : "DBLP",
        auth: "公开元数据",
        detail: "DBLP 适合补齐题录；全文与材料可能需要出版社页面或手动链接。",
        priority: "中"
      };
    }
    return {
      method: item.source || "自定义来源",
      auth: "视来源而定",
      detail: "建议配置 RSS、公开 URL 或导入列表；需要登录时使用本地授权模式。",
      priority: "低"
    };
  }

  function conferenceOptionLabel(item) {
    return item.name || item.label || item.id || item;
  }

  function renderConferenceSettings(sourcePrefs = {}) {
    const target = $("settingConferenceList");
    if (!target) return;
    const configured = new Set(splitListValue(sourcePrefs.conferences || ["ICLR", "NeurIPS", "ACL", "SIGIR"]));
    const sourceConferences = state.sourceOptions?.conferences || [];
    const fallback = Array.from(configured).map((name) => ({ id: name, label: name, enabled: true }));
    const conferences = (sourceConferences.length ? sourceConferences : fallback)
      .filter((item) => conferenceOptionLabel(item))
      .slice(0, 12);

    if (!conferences.length) {
      target.className = "conference-source-list empty";
      target.textContent = "暂无会议源配置。";
      return;
    }

    target.className = "conference-source-list";
    target.innerHTML = conferences.map((item) => {
      const id = item.id || item.name || item.label;
      const label = conferenceOptionLabel(item);
      const info = conferenceAccessInfo(item);
      const checked = configured.size ? configured.has(id) || configured.has(label) : Boolean(item.enabled !== false);
      const disabled = item.enabled === false ? "disabled" : "";
      return `
        <label class="conference-source-item ${checked ? "active" : ""}">
          <input type="checkbox" value="${escapeHtml(id)}" ${checked ? "checked" : ""} ${disabled}>
          <span class="conference-main">
            <strong>${escapeHtml(label)} <em>${escapeHtml(item.group || "会议")}</em></strong>
            <small>${escapeHtml(info.detail)}</small>
            <small>${escapeHtml([item.acceptance_timeline && `公布 ${item.acceptance_timeline}`, item.conference_date && `会议 ${item.conference_date}`, item.venue_id].filter(Boolean).join(" · "))}</small>
          </span>
          <span class="conference-meta">
            <em>${escapeHtml(info.method)}</em>
            <em>${escapeHtml(info.auth)}</em>
            <em>优先级 ${escapeHtml(info.priority)}</em>
          </span>
        </label>
      `;
    }).join("");
  }

  function selectedSettingConferences() {
    return Array.from($("settingConferenceList")?.querySelectorAll("input:checked") || [])
      .map((input) => input.value)
      .filter(Boolean);
  }

  function rssUrls() {
    return Array.from($("customSourcesList").querySelectorAll("strong"))
      .map((item) => item.textContent.trim())
      .filter(Boolean);
  }

  function renderRssUrls(urls) {
    const items = splitListValue(urls);
    $("customSourcesList").innerHTML = items.map((url) => `
      <div><span>rss</span><strong>${escapeHtml(url)}</strong><button data-remove-source type="button">×</button></div>
    `).join("") || `<div><span>rss</span><strong>未配置自定义 RSS</strong><button data-remove-source type="button">×</button></div>`;
  }

  function renderSettings(data) {
    const paths = data.paths || {};
    const storageStats = data.storage_stats || {};
    const rows = [
      ["PDF 缓存目录", paths.pdf_dir],
      ["精读报告目录", paths.reading_reports_dir],
      ["知识库目录", paths.wiki_dir],
      ["写入飞书", paths.write_feishu ? "是" : "否"],
      ["Wiki 增量写入", paths.wiki_ingest ? "是" : "否"]
    ];
    $("settingsList").className = "settings-list";
    $("settingsList").innerHTML = rows.map(([key, value]) => `
      <div class="setting-row"><strong>${escapeHtml(key)}</strong><span>${escapeHtml(value || "-")}</span></div>
    `).join("");
    if ($("cacheSizeStat")) $("cacheSizeStat").textContent = storageStats.cache_display || "-";

    const env = envMap(data);
    const concurrency = envInfo(env, "PAPERFLOW_MAX_CONCURRENCY", "5");
    const model = envInfo(env, "PAPERFLOW_LLM_MODEL", "GPT-4o");
    if ($("maxConcurrencyInput")) $("maxConcurrencyInput").value = concurrency.value || "5";
    if ($("fallbackModelInput")) $("fallbackModelInput").value = model.value || "GPT-4o";
    const sourcePrefs = data.source_preferences || {};
    const reportPrefs = data.report_preferences || {};
    const advanced = data.advanced || {};
    $("settingEnableArxiv").checked = sourcePrefs.enable_arxiv !== false;
    $("settingEnableSemanticScholar").checked = sourcePrefs.enable_semantic_scholar !== false;
    $("settingEnableOpenReview").checked = sourcePrefs.enable_openreview !== false;
    $("settingEnableCustomRss").checked = Boolean(sourcePrefs.enable_custom_rss);
    renderSettingTags("settingArxivCategories", sourcePrefs.arxiv_categories || ["cs.CL", "cs.AI", "cs.IR", "cs.LG"]);
    setConferenceAccessMode(sourcePrefs.conference_access_mode || "public");
    setEnvFieldValue("semanticScholarApiKey", env, "SEMANTIC_SCHOLAR_API_KEY");
    setEnvFieldValue("openReviewUsername", env, "OPENREVIEW_USERNAME");
    setEnvFieldValue("openReviewToken", env, "OPENREVIEW_TOKEN");
    setEnvFieldValue("conferenceCookieFile", env, "PAPERFLOW_CONFERENCE_COOKIE_FILE", "", ["OPENREVIEW_COOKIE_FILE"]);
    updateSourceAuthStatus(sourcePrefs, env);
    renderConferenceSettings(sourcePrefs);
    renderRssUrls(sourcePrefs.custom_rss_urls || []);
    document.querySelectorAll("[data-pref-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.prefMode === (reportPrefs.style || "standard"));
    });
    $("directWriteFeishu").checked = Boolean(reportPrefs.write_feishu);
    $("writeFeishuReports").checked = Boolean(reportPrefs.write_feishu);
    $("directPdfWriteFeishu").checked = Boolean(reportPrefs.write_feishu);
    $("wikiIngestSetting").checked = reportPrefs.wiki_ingest !== false;
    $("dailyLimitInput").value = advanced.daily_limit || 30;
    $("relevanceThreshold").value = advanced.relevance_threshold || 60;
    $("relevanceValue").textContent = $("relevanceThreshold").value;
    $("proxyInput").value = advanced.http_proxy || "";
    $("envSettingsForm").className = "env-form";
    $("envSettingsForm").innerHTML = [
      envRow(env, "PAPERFLOW_LLM_PROVIDER", "LLM Provider", env.OPENAI_API_KEY ? "openai" : ""),
      envRow(env, "PAPERFLOW_LLM_MODEL", "LLM Model"),
      envRow(env, "OPENAI_API_KEY", "OpenAI API Key"),
      envRow(env, "OPENAI_BASE_URL", "OpenAI Base URL"),
      envRow(env, "PAPERFLOW_EMBED_PROVIDER", "Embedding Provider", env.OPENAI_API_KEY ? "openai" : "", ["PAPERFLOW_EMBEDDING_PROVIDER"]),
      envRow(env, "PAPERFLOW_EMBED_MODEL", "Embedding Model", "", ["PAPERFLOW_EMBEDDING_MODEL"]),
      envRow(env, "ANTHROPIC_API_KEY", "Anthropic API Key"),
      envRow(env, "ANTHROPIC_BASE_URL", "Anthropic Base URL")
    ].join("");
  }

  async function loadSettings() {
    const data = await api("/api/settings");
    renderSettings(data);
    await loadCurrentProfile();
  }

  async function saveSettings() {
    const values = {};
    document.querySelectorAll("[data-env-key]").forEach((input) => {
      values[input.dataset.envKey] = input.value;
    });
    if ($("maxConcurrencyInput")) {
      values.PAPERFLOW_MAX_CONCURRENCY = $("maxConcurrencyInput").value;
    }
    values.PAPERFLOW_DEFAULT_ARXIV_CATEGORIES = Array.from($("settingArxivCategories").querySelectorAll("span")).map((item) => item.textContent.trim()).filter(Boolean).join(",");
    values.PAPERFLOW_DEFAULT_CONFERENCES = selectedSettingConferences().join(",");
    values.PAPERFLOW_CUSTOM_RSS_URLS = rssUrls().filter((url) => url !== "未配置自定义 RSS").join(",");
    values.PAPERFLOW_ENABLE_ARXIV = String($("settingEnableArxiv").checked);
    values.PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR = String($("settingEnableSemanticScholar").checked);
    values.PAPERFLOW_ENABLE_OPENREVIEW = String($("settingEnableOpenReview").checked);
    values.PAPERFLOW_ENABLE_CUSTOM_RSS = String($("settingEnableCustomRss").checked);
    values.PAPERFLOW_CONFERENCE_ACCESS_MODE = document.querySelector('input[name="conferenceAccessMode"]:checked')?.value || "public";
    values.PAPERFLOW_REPORT_STYLE = document.querySelector("[data-pref-mode].active")?.dataset.prefMode || "standard";
    values.PAPERFLOW_WRITE_FEISHU = String($("writeFeishuReports").checked || $("directWriteFeishu").checked || $("directPdfWriteFeishu").checked);
    values.PAPERFLOW_WIKI_INGEST = String($("wikiIngestSetting").checked);
    values.PAPERFLOW_DAILY_LIMIT = $("dailyLimitInput").value;
    values.PAPERFLOW_RELEVANCE_THRESHOLD = $("relevanceThreshold").value;
    values.HTTP_PROXY = $("proxyInput").value;
    values.HTTPS_PROXY = $("proxyInput").value;
    const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ values }) });
    renderSettings(data);
  }

  async function testProvider(kind) {
    const data = await api("/api/provider-test", { method: "POST", body: JSON.stringify({ kind }) });
    $("providerTestOutput").className = "answer";
    $("providerTestOutput").textContent = JSON.stringify(data, null, 2);
  }

  function showSettingsMessage(message) {
    $("providerTestOutput").className = "answer";
    $("providerTestOutput").textContent = message;
    setStatus("已更新");
  }

  function addCustomSource() {
    const input = $("sourceUrlInput");
    const value = input.value.trim();
    if (!value) {
      showSettingsMessage("请输入 RSS 或网页 URL。");
      return;
    }
    $("customSourcesList").insertAdjacentHTML("beforeend", `
      <div><span>rss</span><strong>${escapeHtml(value)}</strong><button data-remove-source type="button">×</button></div>
    `);
    input.value = "";
    showSettingsMessage("已加入自定义来源，请点击保存设置写入后端配置。");
  }

  async function exportData(format) {
    const data = await api("/api/export", {
      method: "POST",
      body: JSON.stringify({ user_id: currentUser(), format })
    });
    showSettingsMessage(`已导出 ${data.format}: ${data.display_path || data.path}（${data.count || 0} 项）`);
  }

  async function saveProfile() {
    const userId = $("profileUserId").value.trim() || currentUser();
    const pdfPaths = $("pdfPaths").value.split(";").map((item) => item.trim()).filter(Boolean);
    const data = await api("/api/profile", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        natural_language: $("naturalLanguage").value,
        scholar_url: $("scholarUrl").value,
        homepage_url: $("homepageUrl").value,
        pdf_paths: pdfPaths,
        reset_existing: $("resetProfile").checked
      })
    });
    state.currentUser = userId;
    if (!state.users.some((user) => user.user_id === userId)) {
      state.users.push(normalizeUser(userId));
      await loadUsers();
      $("userSelect").value = userId;
    }
    renderProfileForm(data);
    showSettingsMessage(`已加载 ${userId} 的画像信息。`);
  }

  function bindEvents() {
    document.querySelectorAll(".rail-item").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.view));
    });
    window.addEventListener("hashchange", () => setView(window.location.hash.slice(1) || "papers", false));
    $("refreshUsersBtn").addEventListener("click", () => runAction(async () => {
      await loadUsers();
      await loadCurrentProfile();
    }, "刷新用户"));
    $("userSelect").addEventListener("change", () => {
      state.dailyPollToken += 1;
      setDailyTaskState("", "", false);
      state.currentUser = currentUser();
      runAction(async () => {
        await loadLatestPush();
        await loadWiki();
        await loadCurrentProfile();
        await resumeDailyTask();
      }, "切换用户");
    });

    $("paperDate").value = todayDateValue();
    syncDateControls();
    $("prevDayBtn").addEventListener("click", () => shiftDate(-1));
    $("nextDayBtn").addEventListener("click", () => shiftDate(1));
    $("paperDate").addEventListener("change", syncDateControls);
    $("daysInput").addEventListener("change", syncDateControls);
    $("runDailyBtn").addEventListener("click", () => runAction(runDaily, "拉取论文"));
    $("sortRelevanceBtn").addEventListener("click", () => {
      if (!state.push?.papers) return;
      state.push.papers.sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
      renderPush(state.push);
    });
    $("paperList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      const number = Number(button.dataset.number);
      if (button.dataset.action === "read") {
        runAction(() => readSinglePaper(number), "生成精读报告");
        return;
      } else if (button.dataset.action === "skip") {
        state.skipped.has(number) ? state.skipped.delete(number) : state.skipped.add(number);
        state.selected.delete(number);
        state.later.delete(number);
      } else if (button.dataset.action === "later") {
        state.later.has(number) ? state.later.delete(number) : state.later.add(number);
        state.selected.delete(number);
        state.skipped.delete(number);
      }
      updateSelectionSummary();
    });
    $("selectAllSourcesBtn").addEventListener("click", () => toggleAllSources(true));
    $("clearSourcesBtn").addEventListener("click", () => toggleAllSources(false));
    document.querySelectorAll("[data-source-toggle]").forEach((button) => {
      button.addEventListener("click", () => toggleSourceGroup(button.dataset.sourceToggle));
    });
    $("submitFeedbackBtn").addEventListener("click", () => runAction(() => submitFeedback(false), "提交反馈"));
    $("submitAndReadBtn").addEventListener("click", () => runAction(() => submitFeedback(true), "生成报告"));

    $("refreshReportsBtn").addEventListener("click", () => runAction(() => refreshReports({ keepSelection: false }), "刷新报告"));
    $("reportDays").addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false }), "筛选报告"));
    $("reportDate").addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false }), "筛选报告"));
    $("reportsCurrentOnly").addEventListener("change", () => runAction(() => refreshReports({ keepSelection: false }), "筛选报告"));
    $("reportQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") runAction(() => refreshReports({ keepSelection: false }), "搜索报告");
    });
    $("reportTodayBtn").addEventListener("click", () => {
      $("reportDate").valueAsDate = new Date();
      runAction(() => refreshReports({ keepSelection: false }), "筛选报告");
    });
    $("reportsList").addEventListener("click", (event) => {
      const row = event.target.closest("[data-report-id]");
      if (row) runAction(() => loadReportContent(row.dataset.reportId), "打开报告");
    });
    ["openReportAbsBtn", "openReportPdfBtn", "openReportDocBtn"].forEach((id) => {
      $(id).addEventListener("click", () => {
        const href = $(id).dataset.href;
        if (href) window.open(href, "_blank", "noopener");
      });
    });
    $("copyReportPathBtn").addEventListener("click", async () => {
      const path = $("copyReportPathBtn").dataset.href || "";
      if (navigator.clipboard && path) await navigator.clipboard.writeText(path);
    });
    $("readArxivBtn").addEventListener("click", () => runAction(() => directRead("arxiv"), "生成报告"));
    $("readPdfBtn").addEventListener("click", () => runAction(() => directRead("pdf"), "生成报告"));

    $("refreshWikiBtn").addEventListener("click", () => runAction(loadWiki, "更新 Wiki"));
    $("wikiSearchBtn").addEventListener("click", () => runAction(searchWiki, "搜索 Wiki"));
    document.querySelectorAll("[data-wiki-view]").forEach((button) => {
      button.addEventListener("click", () => setWikiView(button.dataset.wikiView));
    });
    $("wikiQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") runAction(searchWiki, "搜索 Wiki");
    });
    $("wikiGraph").addEventListener("click", (event) => {
      const action = event.target.closest("[data-graph-action]")?.dataset.graphAction;
      const node = event.target.closest("[data-node-title]");
      if (!action && !node) return;
      event.stopImmediatePropagation();
      if (action) {
        $("wikiGraph").classList.toggle("zoomed", action === "zoom-in");
        $("wikiGraph").classList.toggle("compact", action === "zoom-out");
        if (action === "focus") {
          $("wikiGraph").classList.remove("zoomed", "compact");
          const focus = state.wikiMap?.byId?.["architecture:core"];
          if (focus) setWikiEntry(graphTitle(focus), graphBody(focus), graphId(focus), { editNodeId: focus.real_node_id || "" });
        }
        return;
      }
      setWikiEntry(
        node.dataset.nodeTitle,
        node.dataset.nodeBody || `${node.dataset.nodeTitle} 来自当前知识库架构，可继续查看关联论文、上下文和引用来源。`,
        node.dataset.nodeId || "",
        { editNodeId: node.dataset.realNodeId || "" }
      );
    }, true);
    $("wikiResults").addEventListener("click", (event) => {
      const node = event.target.closest("[data-node-title]");
      if (!node) return;
      setWikiEntry(node.dataset.nodeTitle, node.dataset.nodeBody || "", node.dataset.nodeId || "");
    });
    $("editWikiEntryBtn").addEventListener("click", () => runAction(async () => {
      const editor = $("wikiEntryEditor");
      const body = $("wikiEntryBody");
      const editing = editor.hidden;
      if (editing) {
        if (!state.currentWikiNodeId) {
          throw new Error("请选择一个来自当前用户知识库的条目后再编辑。");
        }
        if (!state.currentWikiEditNodeId) {
          throw new Error("这是自动生成的架构节点，请从列表视图或右侧关联论文中选择真实 Wiki 条目后再编辑。");
        }
        editor.value = body.dataset.rawBody || body.textContent;
        editor.hidden = false;
        body.hidden = true;
        $("editWikiEntryBtn").textContent = "保存";
      } else {
        const data = await api("/api/wiki/node", {
          method: "POST",
          body: JSON.stringify({
            user_id: currentUser(),
            node_id: state.currentWikiEditNodeId,
            title: $("wikiEntryTitle").textContent,
            body: editor.value
          })
        });
        body.dataset.rawBody = data.node?.body || editor.value;
        body.innerHTML = renderWikiEntryHtml(body.dataset.rawBody);
        body.hidden = false;
        editor.hidden = true;
        $("editWikiEntryBtn").textContent = "编辑";
        await loadWiki();
      }
    }, "保存 Wiki"));

    $("wikiAskBtn").addEventListener("click", () => runAction(askWiki, "生成回答"));
    $("chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) runAction(askWiki, "生成回答");
    });
    $("chatInput").addEventListener("input", scheduleMentionSearch);
    $("chatInput").addEventListener("click", scheduleMentionSearch);
    $("mentionSuggestions").addEventListener("click", (event) => {
      const button = event.target.closest("[data-mention-node-id]");
      if (!button) return;
      insertMention({
        node_id: button.dataset.mentionNodeId,
        title: button.dataset.title,
        node_type: button.dataset.nodeType
      });
    });
    $("chatMentionChips").addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-mention]");
      if (!button) return;
      const nodeId = button.dataset.removeMention;
      state.chatMentions = state.chatMentions.filter((mention) => mention.node_id !== nodeId);
      renderChatMentionChips();
    });
    $("chatThread").addEventListener("click", (event) => {
      const button = event.target.closest(".citation-ref");
      if (button) focusCitationSource(button.dataset.citationIndex);
    });
    $("chatSources").addEventListener("click", (event) => {
      const openButton = event.target.closest("[data-open-citation-source]");
      const card = event.target.closest(".citation-card");
      if (openButton) {
        runAction(() => openCitationSource(openButton.dataset.nodeId, openButton.dataset.title), "打开引用");
        return;
      }
      if (card && !event.target.closest("a")) {
        runAction(() => openCitationSource(card.dataset.nodeId, card.dataset.title), "打开引用");
      }
    });
    document.querySelectorAll(".quick-prompts button").forEach((button) => {
      button.addEventListener("click", () => {
        $("chatInput").value = button.dataset.prompt || "";
        runAction(askWiki, "生成回答");
      });
    });

    $("refreshSettingsBtn").addEventListener("click", () => runAction(loadSettings, "加载设置"));
    $("saveSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));
    $("testLlmBtn").addEventListener("click", () => runAction(() => testProvider("llm"), "测试 LLM"));
    $("testEmbedBtn").addEventListener("click", () => runAction(() => testProvider("embedding"), "测试 Embedding"));
    document.querySelectorAll('input[name="conferenceAccessMode"]').forEach((input) => {
      input.addEventListener("change", () => syncConferenceAccessUi(input.value));
    });
    $("settingConferenceList").addEventListener("change", (event) => {
      const input = event.target.closest("input[type='checkbox']");
      const item = event.target.closest(".conference-source-item");
      if (input && item) item.classList.toggle("active", input.checked);
    });
    $("saveProfileBtn").addEventListener("click", () => runAction(saveProfile, "保存画像"));
    $("addSourceUrlBtn").addEventListener("click", addCustomSource);
    $("sourceUrlInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter") addCustomSource();
    });
    $("customSourcesList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-source]");
      if (button) button.closest("div")?.remove();
    });
    document.querySelectorAll("[data-pref-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-pref-mode]").forEach((item) => item.classList.toggle("active", item === button));
        showSettingsMessage(`已切换报告偏好：${button.textContent.trim()}`);
      });
    });
    $("relevanceThreshold").addEventListener("input", () => {
      $("relevanceValue").textContent = $("relevanceThreshold").value;
    });
    $("exportMarkdownBtn").addEventListener("click", () => runAction(() => exportData("markdown"), "导出 Markdown"));
    $("exportZipBtn").addEventListener("click", () => runAction(() => exportData("zip"), "导出 ZIP"));
  }

  function shiftDate(days) {
    const input = $("paperDate");
    const date = input.valueAsDate || new Date();
    date.setDate(date.getDate() + days);
    input.valueAsDate = date;
    syncDateControls();
  }

  function toggleAllSources(checked) {
    document.querySelectorAll(".choice-list input[type='checkbox']").forEach((input) => {
      input.checked = checked;
    });
  }

  function toggleSourceGroup(id) {
    const inputs = Array.from($(id).querySelectorAll("input[type='checkbox']"));
    const shouldCheck = inputs.some((input) => !input.checked);
    inputs.forEach((input) => {
      input.checked = shouldCheck;
    });
  }

  async function init() {
    bindEvents();
    renderChatSources();
    await loadHealth();
    await loadUsers();
    await loadSourceOptions();
    await loadLatestPush();
    await loadWiki();
    await loadSettings();
    await resumeDailyTask();
    const initialView = window.location.hash.slice(1) || "papers";
    setView(document.getElementById(initialView) ? initialView : "papers", false);
  }

  window.addEventListener("DOMContentLoaded", () => {
    runAction(init, "初始化");
  });
})();
