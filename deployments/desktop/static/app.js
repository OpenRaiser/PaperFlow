const state = {
  userId: "",
  push: null,
  selected: new Set(),
  skipped: new Set(),
  activity: [],
  roles: [],
  taskLog: [],
  dailyTaskId: "",
  dailyTaskStatus: "",
  dailyTaskPollId: null,
};

const DEMO_MODE =
  new URLSearchParams(window.location.search).get("demo") === "1" ||
  window.location.hostname.endsWith(".github.io");

const DEMO_USER = {
  user_id: "user_demo",
  role_name: "demo",
  description: "LLM agents for scientific discovery, GUI agents, and literature mining.",
  is_current: true,
  source: "preview",
  updated_at: "2026-06-03 09:30:00",
  has_profile: true,
};

const DEMO_PROFILE = {
  user_id: "user_demo",
  version: "0.3",
  updated_at: "2026-06-03 09:30:00",
  core_directions: {
    "scientific agents": 0.92,
    "literature mining": 0.86,
    "gui agents": 0.78,
  },
  top_directions: [
    ["scientific agents", 0.92],
    ["literature mining", 0.86],
    ["gui agents", 0.78],
  ],
  top_topics: [
    ["paper recommendation", 0.88],
    ["research workflow automation", 0.82],
    ["retrieval augmented generation", 0.73],
  ],
  must_read: {
    authors: ["Percy Liang", "Diyi Yang"],
    institutions: ["Stanford", "HKU"],
    keywords: ["scientific discovery", "GUI agent", "paper reading"],
  },
  drift_state: {
    status: "stable",
    short_window_days: 14,
    explanation: "Recent feedback keeps emphasizing scientific reading agents.",
  },
};

const DEMO_PUSH = {
  push_id: "push_demo_20260603_090000",
  push_time: "2026-06-03 09:00:00",
  metadata: {
    paper_count: 4,
    total_fetched: 128,
    fallback_used: false,
  },
  papers: [
    {
      number: 1,
      id: 101,
      title: "Scientific Reading Agents with Longitudinal User Feedback",
      authors: ["Alice Chen", "Mario Li", "PaperFlow Team"],
      category: "high_relevant",
      publish_date: "2026-06-03",
      url: "https://arxiv.org/abs/2606.03963",
      pdf_url: "https://arxiv.org/pdf/2606.03963",
      abstract:
        "A personalized scientific reading agent that combines daily paper ranking, reading reports, and explicit feedback to adapt a local research profile.",
    },
    {
      number: 2,
      id: 102,
      title: "GUI Agents for Evidence-Grounded Research Workflows",
      authors: ["Yun Wang", "Fei Zhao"],
      category: "maybe_interested",
      publish_date: "2026-06-02",
      url: "https://arxiv.org/abs/2606.04001",
      pdf_url: "https://arxiv.org/pdf/2606.04001",
      abstract:
        "This paper studies browser-based agent workspaces that keep human feedback, evidence traces, and document generation in one local workflow.",
    },
    {
      number: 3,
      id: 103,
      title: "Private Research Wikis from Daily Reading Histories",
      authors: ["Nora Smith", "Kai Huang"],
      category: "edge_relevant",
      publish_date: "2026-06-01",
      url: "https://openreview.net/forum?id=paperflow-demo",
      pdf_url: "",
      abstract:
        "A local-first wiki design for turning reading reports, selected papers, skipped papers, and profile drift into searchable personal research memory.",
    },
    {
      number: 4,
      id: 104,
      title: "Monthly Topic Indexing for Obsidian-Based Paper Notes",
      authors: ["Rui Tan", "Mina Park"],
      category: "must_read",
      publish_date: "2026-05-31",
      url: "https://arxiv.org/abs/2605.30353",
      pdf_url: "https://arxiv.org/pdf/2605.30353",
      abstract:
        "The system exports monthly reading summaries and topic indexes so local Markdown notes can be browsed directly in Obsidian.",
    },
  ],
};

const DEMO_ACTIVITY = [
  {
    id: 1,
    push_id: DEMO_PUSH.push_id,
    paper_id: 101,
    paper_title: "Scientific Reading Agents with Longitudinal User Feedback",
    action: "selected",
    action_type: "gui_selected",
    category: "high_relevant",
    timestamp: "2026-06-03 09:12:00",
  },
  {
    id: 2,
    push_id: DEMO_PUSH.push_id,
    paper_id: 103,
    paper_title: "Private Research Wikis from Daily Reading Histories",
    action: "created_report",
    action_type: "created_report",
    category: "reading_report",
    timestamp: "2026-06-03 09:18:00",
  },
  {
    id: 3,
    push_id: DEMO_PUSH.push_id,
    paper_id: null,
    paper_title: "",
    action: "profile_updated",
    action_type: "profile_updated",
    category: "drift",
    timestamp: "2026-06-03 09:19:00",
  },
];

const DEMO_WIKI_NODES = [
  {
    node_id: "paper-demo-reading-agents",
    node_type: "paper",
    title: "Scientific Reading Agents with Longitudinal User Feedback",
    body: "Selected from the daily push. Evidence connects recommendation, reading report generation, and feedback learning.",
    file_path: "data/wiki/user_demo/papers/paper-demo-reading-agents.md",
    keywords: ["scientific agents", "feedback learning"],
    metadata: {},
  },
  {
    node_id: "topic-demo-private-wiki",
    node_type: "topic",
    title: "Private Research Wiki",
    body: "Repeated theme across reading reports: local-first memory, Obsidian-friendly Markdown, and citation-backed RAG.",
    file_path: "data/wiki/user_demo/topics/topic-private-research-wiki.md",
    keywords: ["wiki", "Obsidian", "RAG"],
    metadata: {},
  },
  {
    node_id: "trajectory-demo-2026-w23",
    node_type: "trajectory",
    title: "Trajectory: 2026-W23",
    body: "Recent feedback increases interest in scientific reading agents and GUI-based research workflows.",
    file_path: "data/wiki/user_demo/trajectories/trajectory-demo-2026-w23.md",
    keywords: ["profile drift", "feedback"],
    metadata: {},
  },
];

const $ = (id) => document.getElementById(id);

const ACTION_LABELS = {
  selected: "已选择",
  skipped: "不感兴趣",
  gui_selected: "界面选择",
  gui_skipped: "界面跳过",
  created_report: "生成精读报告",
  profile_updated: "画像更新",
  must_read_update: "必读规则更新",
  add_author: "添加作者规则",
  remove_author: "移除作者规则",
  add_institution: "添加机构规则",
  remove_institution: "移除机构规则",
  add_keyword: "添加关键词规则",
  remove_keyword: "移除关键词规则",
};

const ROLE_ACTION_LABELS = {
  create: "创建",
  switch: "切换",
  delete: "删除",
};

const WIKI_NODE_LABELS = {
  paper: "论文",
  section: "片段",
  trajectory: "轨迹",
  topic: "主题",
};

function labelAction(value) {
  return ACTION_LABELS[value] || value || "";
}

function labelWikiNode(value) {
  return WIKI_NODE_LABELS[value] || value || "";
}

function localizeError(message) {
  const text = String(message || "");
  const replacements = [
    ["Request failed:", "请求失败："],
    ["Not found", "未找到资源"],
    ["Invalid path", "路径无效"],
    ["Invalid JSON body:", "JSON 请求体无效："],
    ["JSON body must be an object", "JSON 请求体必须是对象"],
    ["user_id is required", "请输入用户 ID"],
    ["role_name is required", "请输入角色名"],
    ["action must be create, switch, or delete", "动作必须是创建、切换或删除"],
    ["user_id and push_id are required", "缺少用户 ID 或推送 ID"],
    ["item_type must be author, institution, or keyword", "规则类型必须是作者、机构或关键词"],
    ["action must be add or remove", "动作必须是添加或移除"],
    ["value is required", "请输入规则内容"],
    ["arxiv_id is required", "请输入 arXiv ID 或链接"],
    ["kind must be 'llm' or 'embedding'", "测试类型必须是 llm 或 embedding"],
    ["Profile not found:", "未找到画像："],
    ["Push not found:", "未找到推送："],
    ["Could not fetch arXiv paper:", "无法获取 arXiv 论文："],
    ["PDF not found:", "未找到 PDF："],
  ];
  for (const [source, target] of replacements) {
    if (text.includes(source)) {
      return text.replace(source, target);
    }
  }
  return text;
}

function setStatus(text, busy = false) {
  $("statusText").textContent = busy ? `${text}...` : text;
  addTaskLog(busy ? `${text}...` : text);
}

function addTaskLog(text) {
  if (!text) return;
  state.taskLog.unshift({
    text,
    time: new Date().toLocaleTimeString(),
  });
  state.taskLog = state.taskLog.slice(0, 30);
  renderTaskLog();
}

function renderTaskLog() {
  const target = $("taskLog");
  if (!target) return;
  if (!state.taskLog.length) {
    target.className = "activity-list empty";
    target.textContent = "暂无任务。";
    return;
  }
  target.className = "activity-list";
  target.innerHTML = state.taskLog.map((item) => `
    <div class="activity-item compact">
      <h4>${escapeHtml(item.text)}</h4>
      <p>${escapeHtml(item.time)}</p>
    </div>
  `).join("");
}

async function api(path, options = {}) {
  if (DEMO_MODE) {
    return demoApi(path, options);
  }
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(localizeError(data.error || `Request failed: ${path}`));
  }
  return data;
}

function parseDemoBody(options) {
  if (!options || !options.body) return {};
  try {
    return JSON.parse(options.body);
  } catch (_error) {
    return {};
  }
}

function demoReport(title = "PaperFlow Demo Reading Report", writeFeishu = false) {
  return {
    created_docs: [
      {
        title,
        report_path: "data/reading_reports/demo-reading-report.md",
        pdf_path: "data/papers/demo-paper.pdf",
        url: writeFeishu ? "https://example.com/paperflow-demo-feishu-doc" : "",
        feishu_error: writeFeishu ? "" : "Preview mode does not call Feishu APIs.",
      },
    ],
    count: 1,
    write_feishu_requested: Boolean(writeFeishu),
    feishu_warning: writeFeishu ? "" : "",
  };
}

async function demoApi(path, options = {}) {
  await new Promise((resolve) => window.setTimeout(resolve, 90));
  const url = new URL(path, window.location.origin);
  const body = parseDemoBody(options);
  const route = url.pathname;

  if (route === "/api/health") {
    return { ok: true, database_exists: true };
  }
  if (route === "/api/settings") {
    return {
      ok: true,
      project_root: "GitHub Pages preview",
      database: "mock://paperflow.db",
      paths: {
        pdf_dir: "data/papers",
        reading_reports_dir: "data/reading_reports",
        wiki_dir: "data/wiki",
        monthly_report_dir: "data/wiki/monthly_reports",
        topic_index_dir: "data/wiki/monthly_reports",
        monthly_subdir: true,
        wiki_ingest: true,
        write_feishu: false,
      },
    };
  }
  if (route === "/api/users") {
    return { ok: true, users: [DEMO_USER] };
  }
  if (route === "/api/roles") {
    const roleName = body.role_name || "demo";
    return {
      ok: true,
      roles: [
        {
          name: roleName,
          user_id: roleName === "demo" ? "user_demo" : `user_${roleName}`,
          description: body.description || DEMO_USER.description,
          is_current: true,
        },
      ],
      current_role: roleName,
    };
  }
  if (route === "/api/profile") {
    return { ok: true, profile: { ...DEMO_PROFILE, user_id: body.user_id || url.searchParams.get("user_id") || "user_demo" } };
  }
  if (route === "/api/latest-push") {
    return { ok: true, push: DEMO_PUSH };
  }
  if (route === "/api/daily/start") {
    return {
      ok: true,
      task: {
        task_id: "task_demo_daily",
        status: "completed",
        push: DEMO_PUSH,
        completed_at: "2026-06-03 09:00:02",
      },
    };
  }
  if (route === "/api/daily/status") {
    return { ok: true, task: null };
  }
  if (route === "/api/activity") {
    return { ok: true, activity: DEMO_ACTIVITY };
  }
  if (route === "/api/feedback") {
    return {
      ok: true,
      status: "success",
      push_id: body.push_id || DEMO_PUSH.push_id,
      selected_numbers: body.selected_numbers || [],
      skipped_numbers: body.skipped_numbers || [],
    };
  }
  if (route === "/api/submit") {
    const selected = body.selected_numbers || [];
    const title = selected.length
      ? DEMO_PUSH.papers.find((paper) => paper.number === Number(selected[0]))?.title
      : "PaperFlow Demo Reading Report";
    return {
      ok: true,
      feedback: {
        status: "success",
        selected_numbers: selected,
        skipped_numbers: body.skipped_numbers || [],
      },
      reports: demoReport(title, Boolean(body.write_feishu)),
    };
  }
  if (route === "/api/read/arxiv") {
    return { ok: true, ...demoReport(`arXiv ${body.arxiv_id || "2606.03963"} 精读报告`, Boolean(body.write_feishu)) };
  }
  if (route === "/api/read/pdf") {
    return { ok: true, ...demoReport(body.title || "本地 PDF 精读报告", Boolean(body.write_feishu)) };
  }
  if (route === "/api/must-read") {
    return { ok: true, must_read: DEMO_PROFILE.must_read };
  }
  if (route === "/api/wiki/stats") {
    return {
      ok: true,
      nodes: 42,
      edges: 96,
      citations: 27,
      wiki_dir: "data/wiki/user_demo",
    };
  }
  if (route === "/api/wiki/search") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const nodes = q
      ? DEMO_WIKI_NODES.filter((node) => `${node.title} ${node.body} ${node.keywords.join(" ")}`.toLowerCase().includes(q))
      : DEMO_WIKI_NODES;
    return { ok: true, nodes: nodes.length ? nodes : DEMO_WIKI_NODES };
  }
  if (route === "/api/wiki/ask") {
    return {
      ok: true,
      text:
        "预览回答：你的近期阅读集中在 scientific reading agents、GUI-based research workflows 和 local research wiki。相关证据来自 demo paper 节点、topic 节点和 trajectory 节点。实际本地运行时，这里会引用 data/wiki 中的真实片段。",
      citations: DEMO_WIKI_NODES,
    };
  }
  if (route === "/api/provider-test") {
    const kind = body.kind === "embedding" ? "embedding" : "llm";
    return {
      ok: true,
      kind,
      provider: kind === "embedding" ? "hash-preview" : "mock-preview",
      model: kind === "embedding" ? "hash" : "paperflow-preview",
      response: kind === "embedding" ? "[0.12, -0.04, 0.31, ...]" : "pong",
      prompt_tokens: kind === "llm" ? 23 : undefined,
      completion_tokens: kind === "llm" ? 2 : undefined,
    };
  }

  return { ok: false, error: `Unknown demo API route: ${route}` };
}

function hasUserOption(userId) {
  return [...$("userSelect").options].some((option) => option.value === userId);
}

function setActiveUser(userId) {
  const nextUserId = String(userId || "").trim();
  state.userId = nextUserId;
  if (nextUserId && hasUserOption(nextUserId)) {
    $("userSelect").value = nextUserId;
  }
  $("profileUserId").value = nextUserId || $("profileUserId").value;
  renderRoles(state.roles);
  return state.userId;
}

function activeUser() {
  const select = $("userSelect");
  return setActiveUser(select.value || state.userId);
}

function ensureUser() {
  const userId = activeUser();
  if (!userId) {
    throw new Error("请先创建或选择一个用户画像。");
  }
  return userId;
}

function switchView(name) {
  const targetView = $(name);
  const targetNav = document.querySelector(`[data-view="${name}"]`);
  if (!targetView || !targetNav) return;
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
  targetView.classList.add("active");
  targetNav.classList.add("active");
  $("pageTitle").textContent = targetNav.textContent;
}

function renderUsers(users, preferredUserId = state.userId) {
  const select = $("userSelect");
  select.innerHTML = "";
  if (!users.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无画像";
    select.appendChild(option);
    state.userId = "";
    return;
  }
  const preferred = String(preferredUserId || "").trim();
  const current = users.find((user) => user.is_current);
  const selectedUserId =
    (preferred && users.some((user) => user.user_id === preferred) && preferred) ||
    current?.user_id ||
    users[0].user_id;

  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = user.user_id;
    option.textContent = user.role_name ? `${user.role_name} (${user.user_id})` : user.user_id;
    if (user.user_id === selectedUserId) option.selected = true;
    select.appendChild(option);
  });
  setActiveUser(select.value || selectedUserId);
}

async function loadUsers(preferredUserId = state.userId) {
  const data = await api("/api/users");
  renderUsers(data.users || [], preferredUserId);
}

async function loadRoles() {
  const data = await api("/api/roles");
  state.roles = data.roles || [];
  renderRoles(state.roles);
}

function renderRoles(roles) {
  const target = $("roleList");
  if (!target) return;
  if (!roles.length) {
    target.className = "role-list empty";
    target.textContent = "暂无角色。";
    return;
  }
  target.className = "role-list";
  target.innerHTML = roles.map((role) => `
    <div class="role-card">
      <div>
        <h4>${escapeHtml(role.name || role.user_id)}</h4>
        <p>${escapeHtml(role.user_id || "")}</p>
        <p>${escapeHtml(role.description || "暂无描述")}</p>
      </div>
      <div class="actions">
        ${role.user_id === state.userId ? `<span class="badge blue">当前选择</span>` : ""}
        ${role.is_current ? `<span class="badge green">当前角色</span>` : `<button data-role-action="switch" data-role="${escapeHtml(role.name)}">切换</button>`}
        <button data-role-action="delete" data-role="${escapeHtml(role.name)}">删除</button>
      </div>
    </div>
  `).join("");
  document.querySelectorAll("[data-role-action]").forEach((button) => {
    button.addEventListener("click", () => runAction(() => updateRole(button.dataset.roleAction, button.dataset.role)));
  });
}

async function updateRole(action, roleName) {
  if (!roleName) throw new Error("请输入角色名。");
  setStatus(`${ROLE_ACTION_LABELS[action] || "更新"}角色 ${roleName}`, true);
  const data = await api("/api/roles", {
    method: "POST",
    body: JSON.stringify({ action, role_name: roleName }),
  });
  state.roles = data.roles || [];
  renderRoles(state.roles);
  const active = state.roles.find((role) => role.is_current);
  const nextUserId = active?.user_id || state.userId;
  await loadUsers(nextUserId);
  if (active && active.user_id) {
    setActiveUser(active.user_id);
  }
  await Promise.allSettled([refreshDashboard(), refreshWikiStats(), refreshProfile(), refreshMustRead()]);
  setStatus(ROLE_ACTION_LABELS[action] ? `角色已${ROLE_ACTION_LABELS[action]}` : "角色已更新");
}

async function syncRoleForUser(userId) {
  const role = state.roles.find((item) => item.user_id === userId);
  if (!role || role.is_current) {
    renderRoles(state.roles);
    return;
  }
  const data = await api("/api/roles", {
    method: "POST",
    body: JSON.stringify({ action: "switch", role_name: role.name }),
  });
  state.roles = data.roles || [];
  renderRoles(state.roles);
  await loadUsers(userId);
  setActiveUser(userId);
}

async function createRole() {
  const roleName = $("roleName").value.trim();
  if (!roleName) throw new Error("请输入角色名。");
  setStatus(`创建角色 ${roleName}`, true);
  const data = await api("/api/roles", {
    method: "POST",
    body: JSON.stringify({
      action: "create",
      role_name: roleName,
      description: $("roleDescription").value.trim(),
      feishu_chat_id: $("roleChatId").value.trim(),
    }),
  });
  state.roles = data.roles || [];
  renderRoles(state.roles);
  await loadUsers(state.userId);
  setStatus("角色已创建");
}

function renderProfile(profile) {
  $("profileSnapshot").textContent = JSON.stringify(profile || {}, null, 2);
}

async function refreshProfile() {
  const userId = ensureUser();
  const data = await api(`/api/profile?user_id=${encodeURIComponent(userId)}`);
  renderProfile(data.profile || data.raw || {});
}

function renderPush(push) {
  state.push = push || null;
  state.selected.clear();
  state.skipped.clear();
  $("reportResults").classList.add("hidden");
  $("reportList").innerHTML = "";
  const metadata = push?.metadata || {};
  const fallbackText = metadata.fallback_used
    ? ` | ${metadata.fallback_days || 7} 天兜底${metadata.fallback_relaxed ? "（宽松匹配）" : ""}`
    : "";

  if (!push || !push.papers || !push.papers.length) {
    if (push) {
      $("pushMeta").textContent = `推送 ${push.push_id || ""} | ${push.push_time || "未知时间"} | 0 篇论文${fallbackText}`;
      $("latestPushStat").textContent = "0";
    } else {
      $("pushMeta").textContent = "尚未加载推送。";
      $("latestPushStat").textContent = "-";
    }
    $("paperList").className = "paper-list empty";
    if (push && Number(metadata.total_fetched || 0) > 0) {
      $("paperList").textContent =
        `本次抓取了 ${metadata.total_fetched} 篇候选论文，但没有论文通过当前画像的相关性筛选。可以把天数调大，或调整画像/必读规则后再运行。`;
    } else if (push) {
      $("paperList").textContent = "本轮推送没有可展示的论文。可以把天数调大后再运行。";
    } else {
      $("paperList").textContent = "请先运行每日推送，或加载最近一次推送。";
    }
    updateSelectionSummary();
    return;
  }

  $("pushMeta").textContent = `推送 ${push.push_id} | ${push.push_time || "未知时间"} | ${push.papers.length} 篇论文${fallbackText}`;
  $("latestPushStat").textContent = push.papers.length;
  $("paperList").className = "paper-list";
  $("paperList").innerHTML = "";

  push.papers.forEach((paper) => {
    const card = document.createElement("article");
    card.className = "paper-card";
    const authors = (paper.authors || []).slice(0, 5).join(", ");
    const category = paper.category && paper.category !== "unknown" ? paper.category : "未知";
    const links = [
      paper.url ? `<a href="${paper.url}" target="_blank" rel="noreferrer">原文</a>` : "",
      paper.pdf_url ? `<a href="${paper.pdf_url}" target="_blank" rel="noreferrer">PDF</a>` : "",
    ].filter(Boolean).join(" | ");
    card.innerHTML = `
      <div class="paper-top">
        <div>
          <h4 class="paper-title">${paper.number}. ${escapeHtml(paper.title)}</h4>
          <div class="paper-meta">${escapeHtml(authors || "未知作者")}</div>
        </div>
        <span class="badge blue">${escapeHtml(category)}</span>
      </div>
      <div class="badge-row">
        ${formatDateBadge(paper.publish_date) ? `<span class="badge">${escapeHtml(formatDateBadge(paper.publish_date))}</span>` : ""}
      </div>
      <p class="paper-abstract">${escapeHtml(paper.abstract || "暂无摘要。")}</p>
      <div class="paper-meta">${links}</div>
      <div class="card-actions">
        <label class="checkline">
          <input type="checkbox" data-action="read" data-number="${paper.number}">
          精读
        </label>
        <label class="checkline">
          <input type="checkbox" data-action="skip" data-number="${paper.number}">
          不感兴趣
        </label>
      </div>
    `;
    $("paperList").appendChild(card);
  });

  document.querySelectorAll("[data-action]").forEach((input) => {
    input.addEventListener("change", handlePaperCheck);
  });
  updateSelectionSummary();
}

function handlePaperCheck(event) {
  const input = event.currentTarget;
  const number = Number(input.dataset.number);
  const action = input.dataset.action;
  const other = document.querySelector(
    `[data-number="${number}"][data-action="${action === "read" ? "skip" : "read"}"]`
  );

  if (input.checked && other) other.checked = false;

  state.selected.delete(number);
  state.skipped.delete(number);
  const read = document.querySelector(`[data-number="${number}"][data-action="read"]`);
  const skip = document.querySelector(`[data-number="${number}"][data-action="skip"]`);
  if (read && read.checked) state.selected.add(number);
  if (skip && skip.checked) state.skipped.add(number);
  updateSelectionSummary();
}

function updateSelectionSummary() {
  $("readingQueueStat").textContent = state.selected.size;
  $("selectionSummary").textContent =
    `${state.selected.size} 篇待精读，${state.skipped.size} 篇标记为不感兴趣`;
}

function isChecked(id) {
  const target = $(id);
  return Boolean(target && target.checked);
}

function formatDateBadge(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const dateMatch = text.match(/^(\d{4}-\d{2}-\d{2})/);
  return dateMatch ? dateMatch[1] : text;
}

async function loadLatestPush() {
  const userId = ensureUser();
  setStatus("加载最新推送", true);
  const data = await api(`/api/latest-push?user_id=${encodeURIComponent(userId)}`);
  renderPush(data.push);
  setStatus("最新推送已加载");
}

function stopDailyTaskPolling() {
  if (state.dailyTaskPollId) {
    window.clearTimeout(state.dailyTaskPollId);
    state.dailyTaskPollId = null;
  }
}

function setDailyButtonBusy(busy) {
  const button = $("runDailyBtn");
  if (button) button.disabled = Boolean(busy);
}

function scheduleDailyTaskPolling() {
  stopDailyTaskPolling();
  state.dailyTaskPollId = window.setTimeout(() => {
    refreshDailyTaskStatus({ fromPoll: true }).catch((error) => {
      setDailyButtonBusy(false);
      setStatus(localizeError(error.message || String(error)));
      console.error(error);
    });
  }, 1800);
}

async function handleDailyTask(task, options = {}) {
  if (!task) {
    setDailyButtonBusy(false);
    return;
  }

  const previousStatus = state.dailyTaskStatus;
  state.dailyTaskId = task.task_id || state.dailyTaskId;
  state.dailyTaskStatus = task.status || "";

  if (task.status === "queued" || task.status === "running") {
    setDailyButtonBusy(true);
    if (!options.fromPoll || previousStatus !== task.status) {
      setStatus(task.status === "queued" ? "每日推送排队中" : "每日推送运行中", true);
    } else {
      $("statusText").textContent = "每日推送运行中...";
    }
    scheduleDailyTaskPolling();
    return;
  }

  stopDailyTaskPolling();
  setDailyButtonBusy(false);

  if (task.status === "completed") {
    if (task.push) renderPush(task.push);
    const count = task.push?.papers?.length || 0;
    await Promise.allSettled([refreshDashboard(), refreshWikiStats()]);
    if (!options.silent) {
      setStatus(count ? "每日推送完成" : "每日推送完成，但本轮没有通过筛选的论文");
    }
    return;
  }

  if (task.status === "failed") {
    if (!options.silent) {
      setStatus(task.error || "每日推送失败");
    }
  }
}

async function refreshDailyTaskStatus(options = {}) {
  const userId = activeUser();
  if (!userId && !state.dailyTaskId) return;
  const query = state.dailyTaskId
    ? `task_id=${encodeURIComponent(state.dailyTaskId)}`
    : `user_id=${encodeURIComponent(userId)}`;
  const data = await api(`/api/daily/status?${query}`);
  await handleDailyTask(data.task, options);
}

async function runDaily() {
  const userId = ensureUser();
  const days = Number($("daysInput").value || 1);
  setStatus("启动每日推送", true);
  const data = await api("/api/daily/start", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, days }),
  });
  await handleDailyTask(data.task);
}

async function submit(generateReports) {
  if (!state.push) throw new Error("请先加载一轮推送。");
  if (!state.push.papers || !state.push.papers.length) {
    throw new Error("当前推送没有可提交的论文。");
  }
  const userId = ensureUser();
  const body = {
    user_id: userId,
    push_id: state.push.push_id,
    selected_numbers: [...state.selected],
    skipped_numbers: [...state.skipped],
    generate_reports: generateReports,
    write_feishu: generateReports && isChecked("writeFeishuReports"),
  };
  setStatus(generateReports ? "提交反馈并生成精读" : "提交反馈", true);
  const data = await api(generateReports ? "/api/submit" : "/api/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (generateReports) {
    renderReports(data.reports || {});
  }
  await Promise.allSettled([refreshDashboard(), refreshWikiStats(), refreshProfile()]);
  setStatus(generateReports ? "反馈与精读完成" : "反馈已保存");
}

function renderReports(reports) {
  const docs = reports.created_docs || [];
  $("reportResults").classList.remove("hidden");
  if (!docs.length) {
    $("reportList").className = "empty";
    $("reportList").textContent = "本次没有生成报告。";
    return;
  }
  $("reportList").className = "";
  $("reportList").innerHTML = renderFeishuNotice(reports, docs) + docs.map((doc) => {
    const reportPath = doc.report_path ? `<p>Markdown：<code>${escapeHtml(doc.report_path)}</code></p>` : "";
    const pdfPath = doc.pdf_path ? `<p>PDF：<code>${escapeHtml(doc.pdf_path)}</code></p>` : "";
    const url = doc.url ? `<p><a href="${doc.url}" target="_blank" rel="noreferrer">打开飞书文档</a></p>` : "";
    const error = doc.feishu_error ? `<p class="warning-text">飞书：发送失败，已保留本地报告。</p>` : "";
    return `
      <div class="report-item">
        <h4>${escapeHtml(doc.title || doc.paper?.title || "精读报告")}</h4>
        ${reportPath}
        ${pdfPath}
        ${url}
        ${error}
      </div>
    `;
  }).join("");
}

function renderReportList(targetId, reports) {
  const docs = reports.created_docs || [];
  const target = $(targetId);
  if (!docs.length) {
    target.className = "empty";
    target.textContent = "本次没有生成报告。";
    return;
  }
  target.className = "";
  target.innerHTML = renderFeishuNotice(reports, docs) + docs.map((doc) => {
    const reportPath = doc.report_path ? `<p>Markdown：<code>${escapeHtml(doc.report_path)}</code></p>` : "";
    const pdfPath = doc.pdf_path ? `<p>PDF：<code>${escapeHtml(doc.pdf_path)}</code></p>` : "";
    const url = doc.url ? `<p><a href="${doc.url}" target="_blank" rel="noreferrer">打开飞书文档</a></p>` : "";
    const error = doc.feishu_error ? `<p class="warning-text">飞书：发送失败，已保留本地报告。</p>` : "";
    return `
      <div class="report-item">
        <h4>${escapeHtml(doc.title || doc.paper?.title || "精读报告")}</h4>
        ${reportPath}
        ${pdfPath}
        ${url}
        ${error}
      </div>
    `;
  }).join("");
}

function renderFeishuNotice(reports, docs) {
  const warning = reports.feishu_warning || "";
  const docErrors = docs
    .map((doc) => doc.feishu_error)
    .filter(Boolean);
  if (!warning && !docErrors.length) return "";
  const details = warning || `飞书文档发送失败：${docErrors[0]}`;
  return `
    <div class="notice warning">
      <strong>飞书文档发送失败，本地报告已生成。</strong>
      <p>${escapeHtml(details)}</p>
      <p>请配置飞书相关环境变量，或确认 lark-cli 已安装并登录后再重试。</p>
    </div>
  `;
}

async function readArxivDirect() {
  const userId = ensureUser();
  const arxivId = $("directArxivId").value.trim();
  if (!arxivId) throw new Error("请输入 arXiv ID 或链接。");
  setStatus("生成 arXiv 精读报告", true);
  const data = await api("/api/read/arxiv", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      arxiv_id: arxivId,
      write_feishu: isChecked("directWriteFeishu"),
    }),
  });
  $("directReportResults").classList.remove("hidden");
  renderReportList("directReportList", data);
  await Promise.allSettled([refreshDashboard(), refreshWikiStats()]);
  setStatus("精读报告已生成");
}

async function readPdfDirect() {
  const userId = ensureUser();
  const pdfPath = $("directPdfPath").value.trim();
  if (!pdfPath) throw new Error("请输入 PDF 路径。");
  setStatus("生成 PDF 精读报告", true);
  const data = await api("/api/read/pdf", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      pdf_path: pdfPath,
      title: $("directPdfTitle").value.trim(),
      write_feishu: isChecked("directPdfWriteFeishu"),
    }),
  });
  $("directReportResults").classList.remove("hidden");
  renderReportList("directReportList", data);
  await Promise.allSettled([refreshDashboard(), refreshWikiStats()]);
  setStatus("精读报告已生成");
}

async function refreshDashboard() {
  const userId = activeUser();
  if (!userId) return;
  const [activity, push] = await Promise.allSettled([
    api(`/api/activity?user_id=${encodeURIComponent(userId)}&days=14`),
    api(`/api/latest-push?user_id=${encodeURIComponent(userId)}`),
  ]);
  if (push.status === "fulfilled" && push.value.push) {
    $("latestPushStat").textContent = push.value.push.papers.length;
  }
  if (activity.status === "fulfilled") {
    state.activity = activity.value.activity || [];
    renderActivity(state.activity);
  }
}

function renderActivity(items) {
  renderActivityList("activityList", items.slice(0, 8), "");
  renderActivityList("historyList", items, $("activityFilter") ? $("activityFilter").value : "");
}

function renderActivityList(targetId, items, filter) {
  const target = $(targetId);
  if (!target) return;
  if (filter) {
    items = items.filter((item) => item.action === filter || item.action_type === filter);
  }
  if (!items.length) {
    target.className = "activity-list empty";
    target.textContent = "暂无最近活动。";
    return;
  }
  target.className = "activity-list";
  target.innerHTML = items.map((item) => `
    <div class="activity-item">
      <h4>${escapeHtml(labelAction(item.action))} | ${escapeHtml(labelAction(item.action_type || ""))}</h4>
      <p>${escapeHtml(item.paper_title || item.push_id || "")}</p>
      <p>${escapeHtml(item.timestamp || "")}</p>
    </div>
  `).join("");
}

async function refreshMustRead() {
  const userId = activeUser();
  if (!userId) return;
  const data = await api(`/api/must-read?user_id=${encodeURIComponent(userId)}`);
  renderMustRead(data.must_read || {});
}

function renderMustRead(mustRead) {
  const groups = [
    ["作者", "authors"],
    ["机构", "institutions"],
    ["关键词", "keywords"],
  ];
  $("mustReadList").className = "must-grid";
  $("mustReadList").innerHTML = groups.map(([label, key]) => {
    const values = mustRead[key] || [];
    const body = values.length
      ? values.map((value) => `<span class="pill">${escapeHtml(value)}</span>`).join("")
      : `<span class="empty">空</span>`;
    return `
      <div class="must-card">
        <h4>${label}</h4>
        <div class="pill-list">${body}</div>
      </div>
    `;
  }).join("");
}

async function updateMustRead(action) {
  const userId = ensureUser();
  const itemType = $("mustReadType").value;
  const value = $("mustReadValue").value.trim();
  if (!value) throw new Error("请输入必读规则的值。");
  setStatus(`${action === "add" ? "添加" : "移除"}必读规则`, true);
  const data = await api("/api/must-read", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, item_type: itemType, value, action }),
  });
  renderMustRead(data.must_read || {});
  await refreshProfile();
  setStatus("必读规则已更新");
}

async function refreshWikiStats() {
  const userId = activeUser();
  if (!userId) return;
  const data = await api(`/api/wiki/stats?user_id=${encodeURIComponent(userId)}`);
  $("wikiNodeStat").textContent = data.nodes || 0;
  $("wikiStats").textContent =
    `节点：${data.nodes || 0} | 关系：${data.edges || 0} | 引用：${data.citations || 0} | ${data.wiki_dir || ""}`;
}

async function searchWiki() {
  const userId = ensureUser();
  const q = $("wikiQuery").value || "";
  setStatus("检索知识库", true);
  const data = await api(`/api/wiki/search?user_id=${encodeURIComponent(userId)}&q=${encodeURIComponent(q)}`);
  renderWikiResults(data.nodes || []);
  setStatus("知识库检索完成");
}

function renderWikiResults(nodes) {
  if (!nodes.length) {
    $("wikiResults").className = "result-list empty";
    $("wikiResults").textContent = "没有匹配的知识节点。";
    return;
  }
  $("wikiResults").className = "result-list";
  $("wikiResults").innerHTML = nodes.map((node) => `
    <div class="result-item">
      <h4>${escapeHtml(node.title || node.node_id)}</h4>
      <p>${escapeHtml(labelWikiNode(node.node_type || ""))} | ${escapeHtml(node.file_path || "")}</p>
      <p>${escapeHtml((node.body || "").slice(0, 300))}</p>
    </div>
  `).join("");
}

async function askWiki() {
  const userId = ensureUser();
  const question = $("wikiQuestion").value.trim();
  if (!question) throw new Error("请输入问题。");
  setStatus("询问知识库", true);
  const data = await api("/api/wiki/ask", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, question }),
  });
  $("wikiAnswer").textContent = data.text || "";
  setStatus("知识库回答完成");
}

async function saveProfile() {
  const userId = $("profileUserId").value.trim();
  const pdfPaths = $("pdfPaths").value
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  setStatus("保存画像", true);
  const data = await api("/api/profile", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      natural_language: $("naturalLanguage").value,
      scholar_url: $("scholarUrl").value,
      homepage_url: $("homepageUrl").value,
      pdf_paths: pdfPaths,
      reset_existing: $("resetProfile").checked,
    }),
  });
  await loadUsers(userId);
  setActiveUser(userId);
  renderProfile(data.profile || {});
  setStatus("画像已保存");
}

async function refreshSettings() {
  const data = await api("/api/settings");
  const paths = data.paths || {};
  const rows = [
    ["项目根目录", data.project_root],
    ["数据库", data.database],
    ["PDF 保存目录", paths.pdf_dir],
    ["精读报告目录", paths.reading_reports_dir],
    ["知识库目录", paths.wiki_dir],
    ["按月份分目录", paths.monthly_subdir ? "是" : "否"],
    ["写入知识库", paths.wiki_ingest ? "是" : "否"],
    ["写入飞书文档", paths.write_feishu ? "是" : "否"],
  ];
  $("settingsList").className = "settings-list";
  $("settingsList").innerHTML = rows.map(([key, value]) => `
    <div class="setting-item"><strong>${escapeHtml(key)}</strong><br><code>${escapeHtml(value || "")}</code></div>
  `).join("");
  ["writeFeishuReports", "directWriteFeishu", "directPdfWriteFeishu"].forEach((id) => {
    const target = $(id);
    if (target && !target.dataset.userTouched) {
      target.checked = Boolean(paths.write_feishu);
    }
  });
}

async function testProvider(kind) {
  const label = kind === "embedding" ? "Embedding" : "LLM";
  setStatus(`测试 ${label}`, true);
  const data = await api("/api/provider-test", {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
  $("providerTestOutput").textContent = JSON.stringify(data, null, 2);
  setStatus(`${label} 测试完成`);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });
  document.querySelectorAll("[data-quick-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.quickView));
  });
  $("refreshUsersBtn").addEventListener("click", () => runAction(loadUsers));
  $("userSelect").addEventListener("change", () => {
    runAction(async () => {
      const userId = setActiveUser($("userSelect").value);
      stopDailyTaskPolling();
      state.dailyTaskId = "";
      state.dailyTaskStatus = "";
      setDailyButtonBusy(false);
      await syncRoleForUser(userId);
      await refreshDashboard();
      await refreshWikiStats();
      await refreshProfile();
      await refreshMustRead();
      await loadLatestPush();
      await refreshDailyTaskStatus({ silent: true });
    });
  });
  $("clearTaskLogBtn").addEventListener("click", () => {
    state.taskLog = [];
    renderTaskLog();
  });
  $("refreshDashboardBtn").addEventListener("click", () => runAction(refreshDashboard));
  $("refreshHistoryBtn").addEventListener("click", () => runAction(refreshDashboard));
  $("activityFilter").addEventListener("change", () => renderActivity(state.activity));
  $("loadPushBtn").addEventListener("click", () => runAction(loadLatestPush));
  $("runDailyBtn").addEventListener("click", () => runAction(runDaily));
  $("submitFeedbackBtn").addEventListener("click", () => runAction(() => submit(false)));
  $("submitAndReadBtn").addEventListener("click", () => runAction(() => submit(true)));
  $("readArxivBtn").addEventListener("click", () => runAction(readArxivDirect));
  $("readPdfBtn").addEventListener("click", () => runAction(readPdfDirect));
  $("refreshWikiBtn").addEventListener("click", () => runAction(refreshWikiStats));
  $("wikiSearchBtn").addEventListener("click", () => runAction(searchWiki));
  $("wikiAskBtn").addEventListener("click", () => runAction(askWiki));
  $("refreshMustReadBtn").addEventListener("click", () => runAction(refreshMustRead));
  $("addMustReadBtn").addEventListener("click", () => runAction(() => updateMustRead("add")));
  $("removeMustReadBtn").addEventListener("click", () => runAction(() => updateMustRead("remove")));
  $("refreshRolesBtn").addEventListener("click", () => runAction(loadRoles));
  $("createRoleBtn").addEventListener("click", () => runAction(createRole));
  $("saveProfileBtn").addEventListener("click", () => runAction(saveProfile));
  $("refreshProfileBtn").addEventListener("click", () => runAction(refreshProfile));
  $("refreshSettingsBtn").addEventListener("click", () => runAction(refreshSettings));
  $("testLlmBtn").addEventListener("click", () => runAction(() => testProvider("llm")));
  $("testEmbedBtn").addEventListener("click", () => runAction(() => testProvider("embedding")));
  ["writeFeishuReports", "directWriteFeishu", "directPdfWriteFeishu"].forEach((id) => {
    const target = $(id);
    if (target) {
      target.addEventListener("change", () => {
        target.dataset.userTouched = "true";
      });
    }
  });
}

async function runAction(fn) {
  try {
    await fn();
  } catch (error) {
    setStatus(localizeError(error.message || String(error)));
    console.error(error);
  }
}

async function boot() {
  bindEvents();
  const health = await api("/api/health");
  $("healthText").textContent = DEMO_MODE
    ? "GitHub Pages 预览模式"
    : health.database_exists ? "运行环境就绪" : "请先运行 paperflow init";
  await loadUsers();
  await loadRoles();
  await Promise.allSettled([
    refreshDashboard(),
    refreshWikiStats(),
    refreshSettings(),
    loadLatestPush(),
    refreshProfile(),
    refreshMustRead(),
  ]);
  await refreshDailyTaskStatus({ silent: true });
  if (!["queued", "running"].includes(state.dailyTaskStatus)) {
    setStatus("就绪");
  }
}

boot().catch((error) => {
  setStatus(localizeError(error.message || String(error)));
  $("healthText").textContent = "运行环境检查失败";
});
