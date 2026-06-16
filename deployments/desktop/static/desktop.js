(function () {
  "use strict";

  const DEMO_MODE = new URLSearchParams(window.location.search).get("demo") === "1";
  const LOCALE_KEY = "paperflow.desktop.locale";
  const supportedLocales = new Set(["zh", "en"]);
  const requestedLocale = new URLSearchParams(window.location.search).get("lang");
  const savedLocale = window.localStorage.getItem(LOCALE_KEY);
  const state = {
    locale: supportedLocales.has(requestedLocale) ? requestedLocale : supportedLocales.has(savedLocale) ? savedLocale : "zh",
    users: [],
    currentUser: "user_demo",
    push: null,
    selected: new Set(),
    skipped: new Set(),
    later: new Set(),
    buttonFeedbackTimers: new WeakMap(),
    lastActionButton: null,
    paperReports: new Map(),
    paperReading: new Set(),
    feedbackTimer: null,
    sourceOptionsLoaded: false,
    sourceOptions: null,
    reports: [],
    currentReport: null,
    reportAnnotationRange: null,
    wikiNodes: [],
    wikiGraph: null,
    wikiMap: null,
    wikiStats: null,
    currentWikiNodeId: "",
    currentWikiEditNodeId: "",
    currentWikiEntry: null,
    wikiView: "graph",
    wikiGraphTransform: { scale: 1, x: 0, y: 0 },
    wikiGraphDragMoved: false,
    currentProfile: null,
    profileLoadToken: 0,
    chatSessionId: "",
    chatHistory: [],
    chatHistoryGroups: [],
    chatHistoryLoaded: false,
    chatMessages: [],
    chatSources: [],
    chatLoadToken: 0,
    chatMentions: [],
    mentionSearchTimer: null,
    mentionSearchToken: 0,
    currentView: "",
    dailyTaskId: "",
    dailyTaskUserId: "",
    dailyPollToken: 0,
    dailyPolling: false,
    settings: null
  };

  const i18n = {
    zh: {
      htmlLang: "zh-CN",
      documentTitle: "PaperFlow 本地工作台",
      language: { label: "语言", title: "选择界面语言", zh: "中文", en: "English" },
      common: {
        operationFailed: "操作失败",
        requestFailed: "请求失败",
        notConfigured: "未配置",
        updated: "已更新",
        yes: "是",
        no: "否",
        openLink: "已打开链接",
        copyUnsupported: "当前浏览器不支持剪贴板写入。",
        source: "来源",
        customSource: "自定义来源",
        untitledUser: "未命名用户",
        untitledPaper: "Untitled Paper",
        localTime: "本地时间",
        localPdf: "本地 PDF",
        arxiv: "arXiv"
      },
      nav: { papers: "论文流", reports: "精读报告", wiki: "知识Wiki", chat: "对话", settings: "设置" },
      views: {
        papers: { title: "论文推荐", kicker: "Today's Papers" },
        reports: { title: "精读报告", kicker: "Reading Reports" },
        wiki: { title: "知识 Wiki", kicker: "Knowledge Wiki" },
        chat: { title: "对话问答", kicker: "Chat & Ask" },
        settings: { title: "设置", kicker: "Settings" }
      },
      topbar: { profile: "用户画像", refreshUsers: "刷新用户" },
      status: { ready: "就绪", busy: "处理中", error: "出错" },
      health: { checking: "检查运行环境", demo: "Demo 离线预览", ready: "运行环境就绪", init: "请先初始化" },
      papers: {
        prevDay: "上一天",
        nextDay: "下一天",
        date: "论文日期",
        rangePrefix: "近",
        rangeSuffix: "天",
        daysLabel: "拉取天数",
        pullToday: "拉取今日论文",
        pullSelected: "拉取所选日期论文",
        backgroundRunning: "后台运行中",
        checkingCache: "检查当天缓存",
        candidate: "当前批次候选",
        filtered: "推荐数",
        selected: "已标记精读",
        wikiNodes: "知识节点",
        countUnit: "篇",
        nodeUnit: "个",
        sourceTitle: "论文来源",
        sourceDesc: "离线版可组合 arXiv、会议、期刊与自定义 RSS。",
        selectAll: "全选",
        clear: "清空",
        conference: "会议",
        journal: "期刊",
        toggle: "切换",
        loadingCategories: "正在加载分类",
        loadingConferences: "正在加载会议",
        loadingJournals: "正在加载期刊",
        pushEmpty: "尚未加载推荐批次。",
        listEmpty: "请先拉取今日论文，或加载最近一次推荐。",
        noRecommendations: "暂无推荐论文。",
        sourceFallback: "论文",
        profileMatch: "画像匹配",
        authorPending: "作者信息待补充",
        read: "精读",
        readSelected: "已选精读",
        readReport: "精读报告",
        loading: "加载中",
        skip: "不感兴趣",
        skipped: "已不感兴趣",
        later: "稍后看",
        laterAdded: "已加入稍后看",
        submitFeedback: "提交反馈",
        submitAndRead: "提交并精读",
        submitting: "提交中",
        generating: "生成中",
        selectionHelp: "选择会写入本地反馈；精读报告会进入报告库，并成为 Wiki 的候选知识条目。",
        selectionSummary: (read, skip, later) => `待提交：${read} 篇精读，${skip} 篇不感兴趣，${later} 篇稍后看`,
        taskStatus: (task) => `任务 ${task.task_id || ""} · ${task.status || "queued"} · ${task.progress_phase || "等待后端返回进度"}`,
        taskPending: "后台仍在拉取和排序论文，完成后会显示正式推荐列表。",
        llmUnknownModel: "未识别模型",
        llmNotReadyTitle: "LLM 尚未配置好",
        llmNotReadyDetail: "当前 LLM 会回退到 mock-llm，说明 API Key、Provider 或模型没有配置好。请到“设置”里配置并测试 LLM 后再生成精读报告。",
        llmSmokeFailedTitle: "LLM 烟测失败",
        llmSmokeFailedDetail: "LLM 烟测未通过，请到“设置”里检查模型、API Key 和 Base URL。",
        llmUnavailableTitle: "LLM 配置不可用",
        llmUnavailableDetail: (detail) => `精读报告需要可用 LLM。请到“设置”里测试 LLM：${detail}`,
        loadedCacheTitle: "已加载当天缓存",
        loadedCacheDetail: "今天已经有推荐批次，本次没有重新爬取。",
        stillRunningTitle: "论文拉取仍在后台运行",
        stillRunningDetail: (taskId) => `任务 ${taskId} 会在完成后自动刷新论文流。`,
        pullFailed: "论文拉取失败",
        recentCache: "最近缓存批次",
        batch: "批次",
        recommendations: (count) => `${count} 篇推荐`,
        dailyLimit: (limit) => `每日上限 ${limit}`,
        perSourceLimit: (limit) => `单源上限 ${limit}`,
        threshold: (value) => `阈值 ${value}`,
        sourceCounts: (items) => `来源 ${items.join("/")}`,
        conferenceCount: (count) => `会议 ${count}`,
        journalCount: (count) => `期刊 ${count}`,
        restored: (number) => `论文 ${number} 已恢复为未选择状态。`,
        cancelled: "已取消选择",
        dispositionLabels: { read: "待精读", skip: "不感兴趣", later: "稍后看" },
        markedAs: (label) => `已标记为${label}`,
        dispositionHelp: "同一篇论文只能选择精读、不感兴趣、稍后看中的一种；点击底部按钮后才会提交到后端。",
        emptyFeedbackTitle: "没有新的反馈",
        emptyFeedbackDetail: "请选择精读、不感兴趣或稍后看后再提交。",
        submittedWithReports: (count) => `反馈已提交，已生成 ${count} 篇精读报告`,
        submittedNoReport: "反馈已提交，未生成新报告",
        submitted: "反馈已提交",
        feedbackCounts: (read, skip, later) => `已写入本地反馈：精读 ${read} / 不感兴趣 ${skip} / 稍后看 ${later}`,
        profileWikiUpdated: "用户画像和 Wiki 会根据这些信号更新",
        wikiBackfilled: (count) => `已补写 ${count} 条精读报告到 Wiki`,
        reportEntered: "报告已进入精读报告库",
        loadPushFirst: "请先加载推荐批次",
        submitUnavailableTitle: "无法提交反馈",
        submitUnavailableDetail: "请先拉取今日论文或加载最近一次推荐批次。",
        chooseReadTitle: "请先选择精读论文",
        chooseReadDetail: "先在论文卡片上点击“精读”，再点击“提交并精读”开始生成报告。",
        chooseReadToast: "精读、不感兴趣、稍后看三种状态互斥，只有已选精读的论文会生成报告。",
        submittingReportTitle: "正在提交反馈并生成精读报告",
        submittingFeedbackTitle: "正在提交反馈",
        submittingDetail: "正在写入本地反馈、更新用户方向，并准备同步到 Wiki。",
        submitFailed: "反馈提交失败",
        noSortableTitle: "暂无可排序论文",
        noSortableDetail: "请先拉取或加载推荐批次。",
        sortedTitle: "已按相关性排序",
        sortedDetail: (count) => `当前批次 ${count} 篇论文已重新排列。`,
        allSourcesTitle: "已全选论文来源",
        allSourcesDetail: "下次拉取论文会使用当前已勾选的来源。",
        clearSourcesTitle: "已清空论文来源",
        clearSourcesDetail: "请至少选择一个来源后再拉取论文。",
        toggledSourceTitle: (label) => `已切换${label}`,
        toggledSourceDetail: (count) => `当前组已选择 ${count} 项。`
      },
      reports: {
        listTitle: "报告列表",
        rangeTitle: "时间范围",
        days7: "近 7 天",
        days30: "近 30 天",
        days90: "近 90 天",
        all: "全部",
        refresh: "刷新",
        queryPlaceholder: "搜索标题、arXiv ID 或路径",
        dateFilter: "精确日期筛选",
        currentOnly: "仅看当前画像",
        today: "今天",
        sourcesEmpty: "报告目录尚未加载。",
        listEmpty: "尚未加载报告列表。",
        viewerTitle: "选择一篇报告",
        viewerMeta: "从左侧列表打开报告后，这里显示正文。",
        openAbs: "原文链接",
        openPdf: "PDF 下载",
        openDoc: "飞书文档",
        copyPath: "复制路径",
        bodyEmpty: "尚未选择报告。",
        readArxiv: "精读 arXiv",
        readPdf: "精读本地 PDF",
        arxivPlaceholder: "2606.03963 或 https://arxiv.org/abs/2606.03963",
        pdfTitlePlaceholder: "可选标题",
        generate: "生成报告",
        none: "暂无报告。",
        defaultTitle: "精读报告",
        completed: "已完成",
        directory: (dirs, count) => `报告目录: ${dirs.join(" | ")} · 数量 ${count}`,
        count: (count) => `数量 ${count}`,
        missing: "报告不存在",
        arxivRequiredTitle: "请先填写 arXiv ID",
        arxivRequiredDetail: "支持 2606.03963 或 https://arxiv.org/abs/2606.03963。",
        pdfRequiredTitle: "请先填写 PDF 路径",
        pdfRequiredDetail: "请输入本机可访问的 PDF 文件路径。",
        generatingTitle: (source) => `正在生成${source}精读报告`,
        generatingDetail: "后端正在拉取论文信息、调用模型并写入本地报告库；完成后会自动打开报告。",
        missingReportId: "后端没有返回精读报告 ID，请检查模型 Provider、PDF 路径或本地报告目录。",
        generatedWarning: "报告已生成，飞书同步有警告",
        generatedTitle: "报告已生成",
        generatedToast: "精读报告已生成",
        generationFailed: "报告生成失败",
        noPathTitle: "暂无可复制路径",
        noPathDetail: "请先打开一篇精读报告。",
        copiedPath: "已复制报告路径"
      },
      wiki: {
        graphTitle: "Wiki 架构图",
        refresh: "更新 Wiki",
        search: "搜索",
        graphView: "图谱视图",
        listView: "列表视图",
        viewLabel: "Wiki 视图",
        dailyScope: "Daily Note 范围",
        latestDaily: "最新 Daily Note",
        monthDaily: "指定月份",
        allDaily: "全部 Daily Note",
        monthLabel: "Daily Note 月份",
        queryPlaceholder: "搜索节点、主题、论文或方法",
        statsEmpty: "尚未加载知识库统计。",
        graphLabel: "知识图谱预览",
        currentEntry: "当前条目",
        edit: "编辑",
        save: "保存",
        architecture: "知识库架构",
        architectureBody: "从本地 Wiki 节点、论文关系和用户反馈中整理出当前知识库结构。",
        relatedPapers: "关联论文",
        evidenceWaiting: "等待检索",
        noResults: "暂无检索结果。",
        relatedConcepts: "相关概念",
        tags: ["主题主线", "方法片段", "论文证据", "用户方向"],
        typeLabels: { method: "方法", paper: "论文/报告", frontier: "前沿", topic: "概念" },
        emptyGraphTitle: "暂无可绘制的 Wiki 图谱",
        emptyGraphBody: "先生成精读报告或提交论文反馈，后端会把论文、章节、方法和用户画像写入本地 Wiki。",
        emptyListTitle: "暂无 Wiki 条目",
        emptyListBody: "生成精读报告或提交反馈后，这里会展示本地 Wiki 条目。",
        noSummary: "暂无摘要。",
        graphRealNote: (shown, total, edges) => `真实图谱 · 展示 ${shown} / 全库 ${total} 节点 · ${edges} 条当前关系`,
        graphSearchNote: (source, shown) => `当前检索结果 · ${source} 原始节点 → ${shown} 展示节点`,
        graphDemoNote: "本地预览数据",
        legend: { topic: "概念", method: "方法", paper: "论文/报告", frontier: "画像/前沿" },
        toolsLabel: "图谱工具",
        zoomIn: "放大",
        zoomOut: "缩小",
        focusCenter: "聚焦中心",
        stats: (stats, typeText, dirText, suffix) => `节点 ${stats.nodes || 0} · 关系 ${stats.edges || 0} · 引用 ${stats.citations || 0}${typeText}${dirText}${suffix}`,
        typePart: { paper: "论文", topic: "主题", section: "片段", trajectory: "轨迹" },
        dirPrefix: "目录",
        defaultTags: ["本地 Wiki", "用户画像", "精读报告"],
        noMatch: "没有匹配的知识节点。",
        itemCount: (count) => `${count} 条`,
        relationCount: (count) => `${count} 条关系`,
        graphNodes: "图谱节点",
        architectureFallbackBody: "暂无可展示的用户知识节点。",
        architectureNode: "架构节点",
        restoredSuffix: " · 已用节点列表恢复",
        refreshDetail: (daily, count) => `扫描 Daily Note ${daily.scanned || 0} 个 · 重分类 ${daily.refreshed || 0} 个 · 可视化 ${count} 个`,
        refreshPartial: "Wiki 已更新，部分报告跳过",
        refreshDone: "Wiki 已更新",
        resultsCount: (count) => `${count} 条结果`,
        architectureClickBody: (title) => `${title} 来自当前知识库架构，可继续查看关联论文、上下文和引用来源。`,
        editNoNode: "请选择一个来自当前用户知识库的条目后再编辑。",
        editArchitectureNode: "这是自动生成的架构节点，请从列表视图或右侧关联论文中选择真实 Wiki 条目后再编辑。",
        githubSync: {
          button: "同步 GitHub",
          pulled: "已拉取远端",
          committed: (commit) => `已提交 ${commit || ""}`.trim(),
          pushed: "已推送",
          unchanged: "没有新的笔记改动",
          repoDir: "目录",
          remote: "远端",
          branch: "分支",
          warning: "提醒",
          llmReview: "LLM 校对",
          resultTitle: "GitHub 同步结果",
          successTitle: "GitHub 同步完成",
          failureTitle: "GitHub 同步失败"
        }
      },
      chat: {
        history: "历史对话",
        historyHint: "按日期保存",
        newChat: "新建",
        clear: "清空",
        historyEmpty: "暂无历史对话。",
        intro: "可以围绕最近论文、精读报告和 Wiki 条目提问；回答会列出参考文献。",
        inputPlaceholder: "输入问题，使用 @ 选择论文或 Wiki 节点",
        send: "发送",
        references: "参考文献",
        scope: "对话范围",
        all: "全部知识库",
        recent: "仅最近 7 天",
        profile: "仅当前方向",
        sourceDefault: "参考文献",
        sourceTitle: (index) => `参考文献 ${index}`,
        generating: "正在生成回答...",
        preparing: "准备回答",
        streamOutput: "流式输出",
        directAnswer: "直接回答",
        referencesCount: (count) => `参考文献 · ${count} 条`,
        routing: {
          explicit_mention: "@ 指定来源",
          local_research_context: "本地证据",
          scope_recent: "最近 7 天",
          scope_profile: "当前方向",
          general_question: "通用问题",
          no_local_context_signal: "直接回答",
          mention_required: "需要选择论文"
        },
        openSource: "打开原文",
        viewSource: "查看来源",
        sourcesEmpty: "暂无参考文献。",
        ungrouped: "未分组",
        today: "今天",
        yesterday: "昨天",
        conversations: (count) => `${count} 段对话`,
        historyEmptyDetail: "暂无历史对话。开始提问后会自动保存到本地数据库。",
        newChatTitle: "新对话",
        messageCount: (count) => `${count} 条消息`,
        me: "我",
        backendRestart: "后端需重启",
        historyUnavailable: "当前 GUI 后端还没加载聊天历史接口。请停止后重新运行 PaperFlow GUI，再刷新页面。",
        missingSession: "历史对话不存在",
        noHistoryTitle: "暂无历史对话",
        noHistoryDetail: "当前没有可清空的对话记录。",
        clearConfirm: (count) => `确定清空 ${count} 段历史对话吗？此操作不会删除 Wiki 或精读报告。`,
        clearedTitle: "已清空历史对话",
        clearedDetail: (count) => `删除 ${count} 段对话。`,
        newChatToastTitle: "已新建对话",
        newChatToastDetail: "第一条回答完成后会自动保存到历史。",
        streamUnavailable: "流式问答接口不可用",
        streamFailed: "流式问答失败",
        streamInterruptedText: "流式连接中断，正在切换到完整回答...",
        streamInterruptedError: "流式回答中断，已自动切换到完整回答",
        streamInterruptedTitle: "流式输出中断",
        streamInterruptedDetail: "已自动切换到完整回答。",
        removeMention: (title) => `移除 ${title}`,
        unnamedNode: "未命名节点",
        match: (score) => `匹配 ${score}%`,
        historyRefreshFailedTitle: "历史列表刷新失败",
        historyRestartDetail: "本次回答已完成；请重启 PaperFlow GUI 后端后再使用历史对话。",
        historyReloadDetail: "本次回答已完成，稍后可重新加载历史。",
        generationFailed: (message) => `生成失败：${message}`
      },
      settings: {
        model: "模型与密钥",
        envEmpty: "尚未加载 .env 设置。",
        concurrency: "并发请求",
        fallbackModel: "备用模型",
        testLlm: "测试 LLM",
        testEmbedding: "测试 Embedding",
        save: "保存设置",
        providerTestEmpty: "尚未运行提供商测试。",
        source: "论文来源",
        semanticOptional: "API Key 可选",
        openReviewPublic: "公开优先",
        arxivPublic: "公开 RSS/API",
        customRss: "自定义 RSS",
        customRssHint: "补充会议/期刊",
        arxivCategories: "arXiv 分类",
        conferenceSources: "会议源",
        loadingConferenceSources: "正在加载会议源。",
        accessMode: "会议访问方式",
        publicFirst: "公开源优先",
        publicAggregate: "公开聚合",
        publicAggregateHint: "OpenReview、会议公开页面、arXiv 优先",
        localCredential: "本地授权",
        localCredentialHint: "API Key / token / cookie 文件",
        manualSupplement: "手动补充",
        manualSupplementHint: "RSS、日程 URL、导出的论文列表",
        semanticPlaceholder: "可选：提高限流额度",
        sourceFieldLabels: ["Semantic Scholar API Key", "OpenReview 用户名", "OpenReview Token", "会议 Cookie 文件"],
        openReviewPlaceholder: "可选：公开页面无需填写",
        tokenPlaceholder: "可选：本地保存",
        cookiePlaceholder: "例如 C:\\paperflow\\cookies\\neurips.txt",
        sourceAuthNote: "需要登录的会议源不要混在普通下拉框里；优先使用公开页面、API Key、RSS 或本地 cookie/token 文件路径，凭据只写入本机 .env。",
        addUrl: "添加 URL",
        profile: "研究画像",
        profileSync: "选择用户后自动加载画像",
        profileFields: {
          user: "用户",
          role: "角色",
          version: "版本",
          updatedAt: "更新时间",
          affiliation: "个人机构",
          directions: "关注方向",
          keywords: "关注关键词",
          authors: "关注作者",
          institutions: "关注机构",
          topics: "关注主题",
          drift: "漂移状态",
          notRecorded: "未记录",
          listHint: "用分号或换行分隔",
          weightedHint: "用分号或换行分隔；可写 方向:0.8",
          topicHint: "用分号或换行分隔；可写 主题:0.8",
          loaded: "画像已加载",
          loading: "正在加载画像...",
          missing: "尚未生成画像，可在此补充"
        },
        userPlaceholder: "user_alice",
        homepagePlaceholder: "个人主页 URL",
        pdfPlaceholder: "PDF 路径，用分号分隔",
        resetProfile: "重置已有画像",
        saveProfile: "保存画像",
        reportWiki: "报告与 Wiki",
        standard: "标准",
        deep: "深度技术分析",
        brief: "简要",
        directFeishu: "精读后写入飞书",
        batchFeishu: "批量报告写入飞书",
        pdfFeishu: "PDF 精读写入飞书",
        wikiAuto: "Wiki 自动增量归档",
        notesGitReview: "GitHub 同步前启用 LLM 校对",
        storage: "存储与导出",
        papers: "论文",
        queue: "待读",
        cache: "缓存",
        storageEmpty: "尚未加载运行目录。",
        exportMarkdown: "导出 Markdown",
        exportZip: "导出 ZIP",
        advanced: "高级参数",
        dailyLimit: "每日推荐上限",
        relevance: "相关性阈值",
        authConfigured: "本地授权已配置",
        authWaiting: "等待授权配置",
        manualFirst: "手动补充优先",
        publicFirstStatus: "公开源优先",
        apiKeyConfigured: "API Key 已配置",
        placeholderMissing: "未配置",
        publicOptionalLogin: "公开/可选登录",
        openReviewDetail: "公开论文可抓取；review、discussion 或补充材料可能需要本地授权。",
        public: "公开",
        aclDetail: "论文元数据和 PDF 通常公开，适合直接作为会议源。",
        cvfDetail: "公开论文页面优先；poster/session 信息可通过 RSS 或会议页面补充。",
        publicMetadata: "公开元数据",
        dblpDetail: "DBLP 适合补齐题录；全文与材料可能需要出版社页面或手动链接。",
        sourceDependent: "视来源而定",
        customSourceDetail: "建议配置 RSS、公开 URL 或导入列表；需要登录时使用本地授权模式。",
        priorityHigh: "高",
        priorityMedium: "中",
        priorityLow: "低",
        conferenceGroup: "会议",
        announced: (value) => `公布 ${value}`,
        conferenceDate: (value) => `会议 ${value}`,
        priorityLabel: (value) => `优先级 ${value}`,
        noConferenceSources: "暂无会议源配置。",
        customRssMissing: "未配置自定义 RSS",
        storageRows: {
          notesRoot: "笔记根目录",
          pdf: "PDF 缓存目录",
          reports: "精读报告目录",
          wiki: "知识库目录",
          notesGit: "阅读笔记 Git 目录",
          notesGitRemote: "阅读笔记 GitHub",
          notesGitBranch: "阅读笔记分支",
          feishu: "写入飞书",
          ingest: "Wiki 增量写入"
        },
        settingsSavedMessage: "设置已保存。每日推荐上限、相关性阈值和代理会用于下一次论文拉取；如果当天缓存参数不同，后端会自动重新拉取。",
        settingsSavedToast: "新参数会用于下一次论文拉取，旧缓存参数不一致时会自动刷新。",
        inputUrl: "请输入 RSS 或网页 URL。",
        sourceAdded: "已加入自定义来源，请点击保存设置写入后端配置。",
        exported: (format, path, count) => `已导出 ${format}: ${path}（${count} 项）`,
        profileLoaded: (userId) => `已加载 ${userId} 的画像信息。`,
        sourceRemoved: (label) => `已移除 ${label}，请点击保存设置写入后端配置。`,
        preferenceChanged: (label) => `已切换报告偏好：${label}`
      }
    },
    en: {
      htmlLang: "en-US",
      documentTitle: "PaperFlow Local Workspace",
      language: { label: "Language", title: "Select interface language", zh: "中文", en: "English" },
      common: {
        operationFailed: "Action failed",
        requestFailed: "Request failed",
        notConfigured: "Not configured",
        updated: "Updated",
        yes: "Yes",
        no: "No",
        openLink: "Link opened",
        copyUnsupported: "This browser does not support clipboard writing.",
        source: "Source",
        customSource: "Custom source",
        untitledUser: "Unnamed user",
        untitledPaper: "Untitled Paper",
        localTime: "Local time",
        localPdf: "Local PDF",
        arxiv: "arXiv"
      },
      nav: { papers: "Papers", reports: "Reports", wiki: "Wiki", chat: "Chat", settings: "Settings" },
      views: {
        papers: { title: "Paper Recommendations", kicker: "Today's Papers" },
        reports: { title: "Reading Reports", kicker: "Reading Reports" },
        wiki: { title: "Knowledge Wiki", kicker: "Knowledge Wiki" },
        chat: { title: "Chat & Ask", kicker: "Chat & Ask" },
        settings: { title: "Settings", kicker: "Settings" }
      },
      topbar: { profile: "Profile", refreshUsers: "Refresh users" },
      status: { ready: "Ready", busy: "Working", error: "Error" },
      health: { checking: "Checking runtime", demo: "Demo offline preview", ready: "Runtime ready", init: "Initialize first" },
      papers: {
        prevDay: "Previous day",
        nextDay: "Next day",
        date: "Paper date",
        rangePrefix: "Last",
        rangeSuffix: "days",
        daysLabel: "Fetch days",
        pullToday: "Pull Today's Papers",
        pullSelected: "Pull Selected Date",
        backgroundRunning: "Running",
        checkingCache: "Checking cache",
        candidate: "Candidates",
        filtered: "Recommended",
        selected: "Marked to read",
        wikiNodes: "Wiki nodes",
        countUnit: "papers",
        nodeUnit: "nodes",
        sourceTitle: "Paper Sources",
        sourceDesc: "Offline mode can combine arXiv, conferences, journals, and custom RSS.",
        selectAll: "Select all",
        clear: "Clear",
        conference: "Conferences",
        journal: "Journals",
        toggle: "Toggle",
        loadingCategories: "Loading categories",
        loadingConferences: "Loading conferences",
        loadingJournals: "Loading journals",
        pushEmpty: "No recommendation batch loaded.",
        listEmpty: "Pull today's papers or load the latest recommendation batch.",
        noRecommendations: "No recommended papers.",
        sourceFallback: "Paper",
        profileMatch: "Profile match",
        authorPending: "Author information pending",
        read: "Deep Read",
        readSelected: "Selected",
        readReport: "Report",
        loading: "Loading",
        skip: "Not Interested",
        skipped: "Dismissed",
        later: "Later",
        laterAdded: "Saved for later",
        submitFeedback: "Submit Feedback",
        submitAndRead: "Submit & Read",
        submitting: "Submitting",
        generating: "Generating",
        selectionHelp: "Choices are written to local feedback; reading reports enter the report library and become candidate Wiki entries.",
        selectionSummary: (read, skip, later) => `Pending: ${read} deep-read, ${skip} not interested, ${later} later`,
        taskStatus: (task) => `Task ${task.task_id || ""} · ${task.status || "queued"} · ${task.progress_phase || "waiting for backend progress"}`,
        taskPending: "The backend is still fetching and ranking papers. The official list will appear when it completes.",
        llmUnknownModel: "Unknown model",
        llmNotReadyTitle: "LLM is not configured",
        llmNotReadyDetail: "The LLM is falling back to mock-llm, which means the API key, provider, or model is not configured. Configure and test the LLM in Settings before generating reading reports.",
        llmSmokeFailedTitle: "LLM smoke test failed",
        llmSmokeFailedDetail: "The LLM smoke test failed. Check the model, API key, and base URL in Settings.",
        llmUnavailableTitle: "LLM configuration unavailable",
        llmUnavailableDetail: (detail) => `Reading reports require a working LLM. Test the LLM in Settings: ${detail}`,
        loadedCacheTitle: "Loaded today's cache",
        loadedCacheDetail: "A recommendation batch already exists for today, so no new crawl was started.",
        stillRunningTitle: "Paper pull is still running",
        stillRunningDetail: (taskId) => `Task ${taskId} will refresh the paper stream after it finishes.`,
        pullFailed: "Paper pull failed",
        recentCache: "Recent cached batch",
        batch: "Batch",
        recommendations: (count) => `${count} recommendations`,
        dailyLimit: (limit) => `Daily limit ${limit}`,
        perSourceLimit: (limit) => `Per-source limit ${limit}`,
        threshold: (value) => `Threshold ${value}`,
        sourceCounts: (items) => `Sources ${items.join("/")}`,
        conferenceCount: (count) => `Conferences ${count}`,
        journalCount: (count) => `Journals ${count}`,
        restored: (number) => `Paper ${number} has been restored to the unselected state.`,
        cancelled: "Selection cleared",
        dispositionLabels: { read: "deep read", skip: "not interested", later: "later" },
        markedAs: (label) => `Marked as ${label}`,
        dispositionHelp: "Each paper can only be set to Deep Read, Not Interested, or Later. The choice is sent to the backend only after you submit.",
        emptyFeedbackTitle: "No new feedback",
        emptyFeedbackDetail: "Choose Deep Read, Not Interested, or Later before submitting.",
        submittedWithReports: (count) => `Feedback submitted, generated ${count} reading report${count === 1 ? "" : "s"}`,
        submittedNoReport: "Feedback submitted, no new report generated",
        submitted: "Feedback submitted",
        feedbackCounts: (read, skip, later) => `Saved local feedback: deep read ${read} / not interested ${skip} / later ${later}`,
        profileWikiUpdated: "The user profile and Wiki will update from these signals",
        wikiBackfilled: (count) => `Backfilled ${count} reading report${count === 1 ? "" : "s"} into Wiki`,
        reportEntered: "The report has entered the reading report library",
        loadPushFirst: "Load a recommendation batch first",
        submitUnavailableTitle: "Cannot submit feedback",
        submitUnavailableDetail: "Pull today's papers or load the latest recommendation batch first.",
        chooseReadTitle: "Choose papers to deep read",
        chooseReadDetail: "Click Deep Read on a paper card, then click Submit & Read to generate reports.",
        chooseReadToast: "Deep Read, Not Interested, and Later are mutually exclusive. Only selected Deep Read papers generate reports.",
        submittingReportTitle: "Submitting feedback and generating reading reports",
        submittingFeedbackTitle: "Submitting feedback",
        submittingDetail: "Writing local feedback, updating user direction, and preparing Wiki sync.",
        submitFailed: "Feedback submission failed",
        noSortableTitle: "No papers to sort",
        noSortableDetail: "Pull or load a recommendation batch first.",
        sortedTitle: "Sorted by relevance",
        sortedDetail: (count) => `${count} papers in the current batch were reordered.`,
        allSourcesTitle: "All paper sources selected",
        allSourcesDetail: "The next paper pull will use the currently selected sources.",
        clearSourcesTitle: "Paper sources cleared",
        clearSourcesDetail: "Select at least one source before pulling papers.",
        toggledSourceTitle: (label) => `Toggled ${label}`,
        toggledSourceDetail: (count) => `${count} items are selected in this group.`
      },
      reports: {
        listTitle: "Report List",
        rangeTitle: "Time range",
        days7: "Last 7 days",
        days30: "Last 30 days",
        days90: "Last 90 days",
        all: "All",
        refresh: "Refresh",
        queryPlaceholder: "Search title, arXiv ID, or path",
        dateFilter: "Exact date filter",
        currentOnly: "Current profile only",
        today: "Today",
        sourcesEmpty: "Report directory not loaded.",
        listEmpty: "Report list not loaded.",
        viewerTitle: "Select a report",
        viewerMeta: "Open a report from the left list to read it here.",
        openAbs: "Source Link",
        openPdf: "PDF",
        openDoc: "Feishu Doc",
        copyPath: "Copy Path",
        bodyEmpty: "No report selected.",
        readArxiv: "Read arXiv",
        readPdf: "Read Local PDF",
        arxivPlaceholder: "2606.03963 or https://arxiv.org/abs/2606.03963",
        pdfTitlePlaceholder: "Optional title",
        generate: "Generate Report",
        none: "No reports.",
        defaultTitle: "Reading Report",
        completed: "Completed",
        directory: (dirs, count) => `Report directories: ${dirs.join(" | ")} · Count ${count}`,
        count: (count) => `Count ${count}`,
        missing: "Report not found",
        arxivRequiredTitle: "Enter an arXiv ID",
        arxivRequiredDetail: "Supports 2606.03963 or https://arxiv.org/abs/2606.03963.",
        pdfRequiredTitle: "Enter a PDF path",
        pdfRequiredDetail: "Enter a local PDF file path accessible from this machine.",
        generatingTitle: (source) => `Generating ${source} reading report`,
        generatingDetail: "The backend is fetching paper metadata, calling the model, and writing the local report. The report will open automatically when ready.",
        missingReportId: "The backend did not return a reading report ID. Check the model provider, PDF path, or local report directory.",
        generatedWarning: "Report generated with a Feishu sync warning",
        generatedTitle: "Report generated",
        generatedToast: "Reading report generated",
        generationFailed: "Report generation failed",
        noPathTitle: "No path to copy",
        noPathDetail: "Open a reading report first.",
        copiedPath: "Report path copied"
      },
      wiki: {
        graphTitle: "Wiki Architecture",
        refresh: "Update Wiki",
        search: "Search",
        graphView: "Graph View",
        listView: "List View",
        viewLabel: "Wiki view",
        dailyScope: "Daily Note scope",
        latestDaily: "Latest Daily Note",
        monthDaily: "Specific month",
        allDaily: "All Daily Notes",
        monthLabel: "Daily Note month",
        queryPlaceholder: "Search nodes, topics, papers, or methods",
        statsEmpty: "Wiki statistics not loaded.",
        graphLabel: "Knowledge graph preview",
        currentEntry: "Current Entry",
        edit: "Edit",
        save: "Save",
        architecture: "Knowledge Architecture",
        architectureBody: "The current knowledge structure is assembled from local Wiki nodes, paper relationships, and user feedback.",
        relatedPapers: "Related Papers",
        evidenceWaiting: "Waiting",
        noResults: "No search results.",
        relatedConcepts: "Related Concepts",
        tags: ["Themes", "Methods", "Paper Evidence", "User Direction"],
        typeLabels: { method: "Method", paper: "Paper/Report", frontier: "Frontier", topic: "Concept" },
        emptyGraphTitle: "No Wiki graph to draw",
        emptyGraphBody: "Generate reading reports or submit paper feedback first. The backend will write papers, sections, methods, and profile signals into the local Wiki.",
        emptyListTitle: "No Wiki entries",
        emptyListBody: "After you generate reading reports or submit feedback, local Wiki entries will appear here.",
        noSummary: "No summary.",
        graphRealNote: (shown, total, edges) => `Real graph · showing ${shown} / ${total} nodes · ${edges} active relations`,
        graphSearchNote: (source, shown) => `Search results · ${source} source nodes → ${shown} displayed nodes`,
        graphDemoNote: "Local preview data",
        legend: { topic: "Concept", method: "Method", paper: "Paper/Report", frontier: "Profile/Frontier" },
        toolsLabel: "Graph tools",
        zoomIn: "Zoom in",
        zoomOut: "Zoom out",
        focusCenter: "Focus center",
        stats: (stats, typeText, dirText, suffix) => `Nodes ${stats.nodes || 0} · Relations ${stats.edges || 0} · Citations ${stats.citations || 0}${typeText}${dirText}${suffix}`,
        typePart: { paper: "papers", topic: "topics", section: "snippets", trajectory: "trajectories" },
        dirPrefix: "dir",
        defaultTags: ["Local Wiki", "User profile", "Reading reports"],
        noMatch: "No matching knowledge nodes.",
        itemCount: (count) => `${count} item${count === 1 ? "" : "s"}`,
        relationCount: (count) => `${count} relation${count === 1 ? "" : "s"}`,
        graphNodes: "Graph nodes",
        architectureFallbackBody: "No user knowledge nodes are available yet.",
        architectureNode: "Architecture node",
        restoredSuffix: " · recovered from node list",
        refreshDetail: (daily, count) => `Scanned ${daily.scanned || 0} Daily Notes · reclassified ${daily.refreshed || 0} · visualized ${count}`,
        refreshPartial: "Wiki updated, some reports were skipped",
        refreshDone: "Wiki updated",
        resultsCount: (count) => `${count} result${count === 1 ? "" : "s"}`,
        architectureClickBody: (title) => `${title} comes from the current knowledge architecture. You can continue to inspect related papers, context, and citation sources.`,
        editNoNode: "Select an entry from the current user's Wiki before editing.",
        editArchitectureNode: "This is an auto-generated architecture node. Choose a real Wiki entry from the list view or related papers before editing.",
        githubSync: {
          button: "Sync GitHub",
          pulled: "Pulled remote",
          committed: (commit) => `Committed ${commit || ""}`.trim(),
          pushed: "Pushed",
          unchanged: "No new note changes",
          repoDir: "Directory",
          remote: "Remote",
          branch: "Branch",
          warning: "Notice",
          llmReview: "LLM review",
          resultTitle: "GitHub sync result",
          successTitle: "GitHub sync completed",
          failureTitle: "GitHub sync failed"
        }
      },
      chat: {
        history: "Chat History",
        historyHint: "Saved by date",
        newChat: "New",
        clear: "Clear",
        historyEmpty: "No chat history.",
        intro: "Ask about recent papers, reading reports, and Wiki entries. Answers include references.",
        inputPlaceholder: "Ask a question; use @ to select papers or Wiki nodes",
        send: "Send",
        references: "References",
        scope: "Scope",
        all: "All knowledge",
        recent: "Last 7 days only",
        profile: "Current direction only",
        sourceDefault: "Reference",
        sourceTitle: (index) => `Reference ${index}`,
        generating: "Generating answer...",
        preparing: "Preparing answer",
        streamOutput: "Streaming",
        directAnswer: "Direct answer",
        referencesCount: (count) => `References · ${count}`,
        routing: {
          explicit_mention: "@ selected source",
          local_research_context: "Local evidence",
          scope_recent: "Last 7 days",
          scope_profile: "Current direction",
          general_question: "General question",
          no_local_context_signal: "Direct answer",
          mention_required: "Paper selection required"
        },
        openSource: "Open source",
        viewSource: "View source",
        sourcesEmpty: "No references.",
        ungrouped: "Ungrouped",
        today: "Today",
        yesterday: "Yesterday",
        conversations: (count) => `${count} conversation${count === 1 ? "" : "s"}`,
        historyEmptyDetail: "No chat history yet. Questions are saved to the local database after you ask.",
        newChatTitle: "New chat",
        messageCount: (count) => `${count} message${count === 1 ? "" : "s"}`,
        me: "Me",
        backendRestart: "Restart backend",
        historyUnavailable: "The current GUI backend has not loaded chat history routes yet. Stop and rerun PaperFlow GUI, then refresh this page.",
        missingSession: "Chat session not found",
        noHistoryTitle: "No chat history",
        noHistoryDetail: "There are no conversations to clear.",
        clearConfirm: (count) => `Clear ${count} conversation${count === 1 ? "" : "s"}? This will not delete Wiki entries or reading reports.`,
        clearedTitle: "Chat history cleared",
        clearedDetail: (count) => `Deleted ${count} conversation${count === 1 ? "" : "s"}.`,
        newChatToastTitle: "New chat started",
        newChatToastDetail: "The first completed answer will be saved to history.",
        streamUnavailable: "Streaming Q&A route is unavailable",
        streamFailed: "Streaming Q&A failed",
        streamInterruptedText: "The streaming connection stopped. Switching to the complete answer...",
        streamInterruptedError: "Streaming answer stopped; switched to the complete answer",
        streamInterruptedTitle: "Streaming interrupted",
        streamInterruptedDetail: "Switched to the complete answer.",
        removeMention: (title) => `Remove ${title}`,
        unnamedNode: "Unnamed node",
        match: (score) => `Match ${score}%`,
        historyRefreshFailedTitle: "Chat history refresh failed",
        historyRestartDetail: "This answer is complete. Restart the PaperFlow GUI backend before using chat history.",
        historyReloadDetail: "This answer is complete. You can reload history later.",
        generationFailed: (message) => `Generation failed: ${message}`
      },
      settings: {
        model: "Models & Keys",
        envEmpty: ".env settings not loaded.",
        concurrency: "Concurrency",
        fallbackModel: "Fallback model",
        testLlm: "Test LLM",
        testEmbedding: "Test Embedding",
        save: "Save Settings",
        providerTestEmpty: "Provider test has not run.",
        source: "Paper Sources",
        semanticOptional: "API key optional",
        openReviewPublic: "Public first",
        arxivPublic: "Public RSS/API",
        customRss: "Custom RSS",
        customRssHint: "Add conferences/journals",
        arxivCategories: "arXiv Categories",
        conferenceSources: "Conference Sources",
        loadingConferenceSources: "Loading conference sources.",
        accessMode: "Conference Access",
        publicFirst: "Public sources first",
        publicAggregate: "Public Aggregation",
        publicAggregateHint: "OpenReview, public conference pages, arXiv first",
        localCredential: "Local Credentials",
        localCredentialHint: "API key / token / cookie file",
        manualSupplement: "Manual Supplement",
        manualSupplementHint: "RSS, schedule URL, exported paper list",
        semanticPlaceholder: "Optional: raise rate limits",
        sourceFieldLabels: ["Semantic Scholar API Key", "OpenReview username", "OpenReview token", "Conference cookie file"],
        openReviewPlaceholder: "Optional: public pages need no username",
        tokenPlaceholder: "Optional: saved locally",
        cookiePlaceholder: "e.g. C:\\paperflow\\cookies\\neurips.txt",
        sourceAuthNote: "Do not mix login-only conference sources into the plain dropdown. Prefer public pages, API keys, RSS, or local cookie/token file paths; credentials are written only to local .env.",
        addUrl: "Add URL",
        profile: "Research Profile",
        profileSync: "Profile loads after user selection",
        profileFields: {
          user: "User",
          role: "Role",
          version: "Version",
          updatedAt: "Updated",
          affiliation: "Affiliation",
          directions: "Directions",
          keywords: "Keywords",
          authors: "Authors",
          institutions: "Institutions",
          topics: "Topics",
          drift: "Drift State",
          notRecorded: "Not recorded",
          listHint: "Separate items with semicolons or new lines",
          weightedHint: "Separate items with semicolons or new lines; supports direction:0.8",
          topicHint: "Separate items with semicolons or new lines; supports topic:0.8",
          loaded: "Profile loaded",
          loading: "Loading profile...",
          missing: "No profile yet; fill it in here"
        },
        userPlaceholder: "user_alice",
        homepagePlaceholder: "Homepage URL",
        pdfPlaceholder: "PDF paths separated by semicolons",
        resetProfile: "Reset existing profile",
        saveProfile: "Save Profile",
        reportWiki: "Reports & Wiki",
        standard: "Standard",
        deep: "Deep Technical Analysis",
        brief: "Brief",
        directFeishu: "Write deep reads to Feishu",
        batchFeishu: "Write batch reports to Feishu",
        pdfFeishu: "Write PDF reads to Feishu",
        wikiAuto: "Auto-ingest Wiki updates",
        notesGitReview: "Enable LLM review before GitHub sync",
        storage: "Storage & Export",
        papers: "Papers",
        queue: "Queue",
        cache: "Cache",
        storageEmpty: "Runtime directories not loaded.",
        exportMarkdown: "Export Markdown",
        exportZip: "Export ZIP",
        advanced: "Advanced",
        dailyLimit: "Daily recommendation limit",
        relevance: "Relevance threshold",
        authConfigured: "Local credentials configured",
        authWaiting: "Waiting for credentials",
        manualFirst: "Manual supplement first",
        publicFirstStatus: "Public sources first",
        apiKeyConfigured: "API key configured",
        placeholderMissing: "Not configured",
        publicOptionalLogin: "Public / optional login",
        openReviewDetail: "Public papers can be crawled; reviews, discussions, or supplementary material may require local credentials.",
        public: "Public",
        aclDetail: "Paper metadata and PDFs are usually public, so this works well as a conference source.",
        cvfDetail: "Public paper pages first; poster/session details can be supplemented via RSS or conference pages.",
        publicMetadata: "Public metadata",
        dblpDetail: "DBLP is useful for bibliographic records; full text and materials may require publisher pages or manual links.",
        sourceDependent: "Depends on source",
        customSourceDetail: "Configure RSS, public URLs, or imported lists; use local credential mode for login-only sources.",
        priorityHigh: "High",
        priorityMedium: "Medium",
        priorityLow: "Low",
        conferenceGroup: "Conference",
        announced: (value) => `Announced ${value}`,
        conferenceDate: (value) => `Conference ${value}`,
        priorityLabel: (value) => `Priority ${value}`,
        noConferenceSources: "No conference source configuration.",
        customRssMissing: "No custom RSS configured",
        storageRows: {
          notesRoot: "Notes root directory",
          pdf: "PDF cache directory",
          reports: "Reading reports directory",
          wiki: "Knowledge base directory",
          notesGit: "Reading notes Git directory",
          notesGitRemote: "Reading notes GitHub remote",
          notesGitBranch: "Reading notes branch",
          feishu: "Write to Feishu",
          ingest: "Wiki incremental ingest"
        },
        settingsSavedMessage: "Settings saved. Daily limit, relevance threshold, and proxy settings will be used on the next paper pull. If today's cache was created with different parameters, the backend will refresh automatically.",
        settingsSavedToast: "New parameters will be used on the next paper pull; stale cache parameters will trigger an automatic refresh.",
        inputUrl: "Enter an RSS or web URL.",
        sourceAdded: "Custom source added. Click Save Settings to write it to backend configuration.",
        exported: (format, path, count) => `Exported ${format}: ${path} (${count} item${count === 1 ? "" : "s"})`,
        profileLoaded: (userId) => `Loaded profile information for ${userId}.`,
        sourceRemoved: (label) => `Removed ${label}. Click Save Settings to write it to backend configuration.`,
        preferenceChanged: (label) => `Report preference changed: ${label}`
      }
    }
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

  const demoChatSessions = [];
  const demoChatMessages = {};

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

  function ui() {
    return i18n[state.locale] || i18n.zh;
  }

  function statusText(message) {
    if (state.locale !== "en") return message;
    return {
      "初始化": "Initializing",
      "刷新用户": "Refreshing users",
      "切换用户": "Switching user",
      "拉取论文": "Pulling papers",
      "选择精读论文": "Selecting paper",
      "提交反馈": "Submitting feedback",
      "生成报告": "Generating report",
      "加载报告": "Loading reports",
      "刷新报告": "Refreshing reports",
      "筛选报告": "Filtering reports",
      "搜索报告": "Searching reports",
      "打开报告": "Opening report",
      "复制路径": "Copying path",
      "加载 Wiki": "Loading Wiki",
      "更新 Wiki": "Updating Wiki",
      "搜索 Wiki": "Searching Wiki",
      "保存 Wiki": "Saving Wiki",
      "生成回答": "Generating answer",
      "新建对话": "Starting chat",
      "清空历史": "Clearing history",
      "打开历史对话": "Opening chat",
      "打开引用": "Opening reference",
      "加载设置": "Loading settings",
      "保存设置": "Saving settings",
      "测试 LLM": "Testing LLM",
      "测试 Embedding": "Testing embedding",
      "保存画像": "Saving profile",
      "导出 Markdown": "Exporting Markdown",
      "导出 ZIP": "Exporting ZIP",
      "已更新": "Updated"
    }[message] || message;
  }

  function setText(selector, value) {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
  }

  function setAllText(selector, values) {
    document.querySelectorAll(selector).forEach((element, index) => {
      if (values[index] !== undefined) element.textContent = values[index];
    });
  }

  function setLabelTexts(selector, values) {
    document.querySelectorAll(selector).forEach((element, index) => {
      const value = values[index];
      if (value === undefined) return;
      const node = Array.from(element.childNodes).find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
      if (!node) {
        element.appendChild(document.createTextNode(` ${value}`));
        return;
      }
      const prefix = node.previousSibling ? " " : "";
      const suffix = node.nextSibling ? " " : "";
      node.textContent = `${prefix}${value}${suffix}`;
    });
  }

  function setAttr(selector, attr, value) {
    const element = document.querySelector(selector);
    if (element) element.setAttribute(attr, value);
  }

  function updatePageTitle() {
    const viewId = state.currentView || document.querySelector(".view.active")?.id || "papers";
    const view = ui().views[viewId] || ui().views.papers;
    if ($("pageTitle")) $("pageTitle").textContent = view.title;
    if ($("pageKicker")) $("pageKicker").textContent = view.kicker;
  }

  function applyLocale() {
    const text = ui();
    document.documentElement.lang = text.htmlLang;
    document.title = text.documentTitle;

    if ($("languageLabel")) $("languageLabel").textContent = text.language.label;
    const languageSelect = $("languageSelect");
    if (languageSelect) {
      languageSelect.value = state.locale;
      languageSelect.title = text.language.title;
      languageSelect.setAttribute("aria-label", text.language.title);
      setAllText("#languageSelect option", [text.language.zh, text.language.en]);
    }

    Object.entries(text.nav).forEach(([view, label]) => {
      setText(`.rail-item[data-view="${view}"] span:last-child`, label);
      setAttr(`.rail-item[data-view="${view}"]`, "title", label);
    });

    setText(".user-picker span", text.topbar.profile);
    setAttr("#userSelect", "aria-label", text.topbar.profile);
    setAttr("#refreshUsersBtn", "title", text.topbar.refreshUsers);
    setAttr("#refreshUsersBtn", "aria-label", text.topbar.refreshUsers);
    if ([i18n.zh.status.ready, i18n.en.status.ready].includes($("statusText")?.textContent)) setStatus(text.status.ready);
    if ([i18n.zh.status.error, i18n.en.status.error].includes($("statusText")?.textContent)) setStatus(text.status.error);

    setAttr("#prevDayBtn", "title", text.papers.prevDay);
    setAttr("#prevDayBtn", "aria-label", text.papers.prevDay);
    setAttr("#nextDayBtn", "title", text.papers.nextDay);
    setAttr("#nextDayBtn", "aria-label", text.papers.nextDay);
    setAttr("#paperDate", "aria-label", text.papers.date);
    setText(".days-control span:first-child", text.papers.rangePrefix);
    setText(".days-control span:last-child", text.papers.rangeSuffix);
    setAttr("#daysInput", "aria-label", text.papers.daysLabel);
    setAllText(".metric-strip div span", [text.papers.candidate, text.papers.filtered, text.papers.selected, text.papers.wikiNodes]);
    setAllText(".metric-strip div em", [text.papers.countUnit, text.papers.countUnit, text.papers.countUnit, text.papers.nodeUnit]);
    setText(".source-toolbar strong", text.papers.sourceTitle);
    setText(".source-toolbar span", text.papers.sourceDesc);
    setText("#selectAllSourcesBtn", text.papers.selectAll);
    setText("#clearSourcesBtn", text.papers.clear);
    setAllText(".source-head strong", ["arXiv", text.papers.conference, text.papers.journal]);
    document.querySelectorAll("[data-source-toggle]").forEach((button) => {
      button.textContent = text.papers.toggle;
    });
    if ($("arxivCategories")?.classList.contains("empty")) $("arxivCategories").textContent = text.papers.loadingCategories;
    if ($("conferenceSources")?.classList.contains("empty")) $("conferenceSources").textContent = text.papers.loadingConferences;
    if ($("journalSources")?.classList.contains("empty")) $("journalSources").textContent = text.papers.loadingJournals;
    if ($("pushMeta")?.classList.contains("empty") || $("pushMeta")?.textContent === i18n.zh.papers.pushEmpty || $("pushMeta")?.textContent === i18n.en.papers.pushEmpty) $("pushMeta").textContent = text.papers.pushEmpty;
    if ($("paperList")?.classList.contains("empty") && !$("paperList")?.classList.contains("syncing")) $("paperList").textContent = text.papers.listEmpty;
    setText(".submit-bar p", text.papers.selectionHelp);
    if ($("submitFeedbackBtn") && !$("submitFeedbackBtn").disabled) $("submitFeedbackBtn").textContent = text.papers.submitFeedback;
    if ($("submitAndReadBtn") && !$("submitAndReadBtn").disabled) $("submitAndReadBtn").textContent = text.papers.submitAndRead;

    setText(".report-list-pane .pane-head h2", text.reports.listTitle);
    setAttr("#reportDays", "title", text.reports.rangeTitle);
    setAllText("#reportDays option", [text.reports.days7, text.reports.days30, text.reports.days90, text.reports.all]);
    setText("#refreshReportsBtn", text.reports.refresh);
    setAttr("#reportQuery", "placeholder", text.reports.queryPlaceholder);
    setAttr("#reportDate", "aria-label", text.reports.dateFilter);
    const reportCurrentLabel = document.querySelector("#reportsCurrentOnly")?.parentElement;
    if (reportCurrentLabel) reportCurrentLabel.lastChild.textContent = ` ${text.reports.currentOnly}`;
    setText("#reportTodayBtn", text.reports.today);
    if ($("reportSources")?.classList.contains("empty") || $("reportSources")?.textContent === i18n.zh.reports.sourcesEmpty || $("reportSources")?.textContent === i18n.en.reports.sourcesEmpty) $("reportSources").textContent = text.reports.sourcesEmpty;
    if ($("reportsList")?.classList.contains("empty")) $("reportsList").textContent = text.reports.listEmpty;
    if (!state.currentReport) {
      setText("#reportViewerTitle", text.reports.viewerTitle);
      setText("#reportViewerMeta", text.reports.viewerMeta);
      setText("#reportViewerBody", text.reports.bodyEmpty);
    }
    setText("#openReportAbsBtn", text.reports.openAbs);
    setText("#openReportPdfBtn", text.reports.openPdf);
    setText("#openReportDocBtn", text.reports.openDoc);
    setText("#copyReportPathBtn", text.reports.copyPath);
    setText(".direct-card:nth-child(1) h3", text.reports.readArxiv);
    setText(".direct-card:nth-child(2) h3", text.reports.readPdf);
    setAttr("#directArxivId", "placeholder", text.reports.arxivPlaceholder);
    setAttr("#directPdfTitle", "placeholder", text.reports.pdfTitlePlaceholder);
    setText("#readArxivBtn", text.reports.generate);
    setText("#readPdfBtn", text.reports.generate);

    setText(".wiki-main .pane-head h2", text.wiki.graphTitle);
    setText("#refreshWikiBtn", text.wiki.refresh);
    setText("#syncGithubBtn", text.wiki.githubSync.button);
    setText("#wikiSearchBtn", text.wiki.search);
    setAllText("[data-wiki-view]", [text.wiki.graphView, text.wiki.listView]);
    setAttr(".wiki-toolbar .segmented", "aria-label", text.wiki.viewLabel);
    setAttr("#wikiDailyScope", "aria-label", text.wiki.dailyScope);
    setAllText("#wikiDailyScope option", [text.wiki.latestDaily, text.wiki.monthDaily, text.wiki.allDaily]);
    setAttr("#wikiDailyMonth", "aria-label", text.wiki.monthLabel);
    setAttr("#wikiQuery", "placeholder", text.wiki.queryPlaceholder);
    if ($("wikiStats")?.textContent === i18n.zh.wiki.statsEmpty || $("wikiStats")?.textContent === i18n.en.wiki.statsEmpty) $("wikiStats").textContent = text.wiki.statsEmpty;
    setAttr("#wikiGraph", "aria-label", text.wiki.graphLabel);
    setText(".document-label", text.wiki.currentEntry);
    if ($("editWikiEntryBtn")) $("editWikiEntryBtn").textContent = $("wikiEntryEditor")?.hidden === false ? text.wiki.save : text.wiki.edit;
    if ($("wikiEntryTitle")?.textContent === i18n.zh.wiki.architecture || $("wikiEntryTitle")?.textContent === i18n.en.wiki.architecture) $("wikiEntryTitle").textContent = text.wiki.architecture;
    if ($("wikiEntryBody")?.textContent === i18n.zh.wiki.architectureBody || $("wikiEntryBody")?.textContent === i18n.en.wiki.architectureBody) $("wikiEntryBody").textContent = text.wiki.architectureBody;
    setText(".related-head h2", text.wiki.relatedPapers);
    if ($("wikiEvidenceSummary")?.textContent === i18n.zh.wiki.evidenceWaiting || $("wikiEvidenceSummary")?.textContent === i18n.en.wiki.evidenceWaiting) $("wikiEvidenceSummary").textContent = text.wiki.evidenceWaiting;
    if ($("wikiResults")?.classList.contains("empty")) $("wikiResults").textContent = text.wiki.noResults;
    setText(".wiki-evidence-pane > h2", text.wiki.relatedConcepts);
    setAllText("#wikiTags span", text.wiki.tags);

    setText(".chat-history-head h2", text.chat.history);
    if ($("chatHistoryHint")?.textContent === i18n.zh.chat.historyHint || $("chatHistoryHint")?.textContent === i18n.en.chat.historyHint) $("chatHistoryHint").textContent = text.chat.historyHint;
    setText("#newChatBtn", text.chat.newChat);
    setText("#clearChatHistoryBtn", text.chat.clear);
    if ($("chatHistoryList")?.classList.contains("empty")) $("chatHistoryList").textContent = text.chat.historyEmpty;
    const intro = document.querySelector("#chatThread .message.assistant .bubble p");
    if (intro && (intro.textContent === i18n.zh.chat.intro || intro.textContent === i18n.en.chat.intro)) intro.textContent = text.chat.intro;
    setAttr("#chatInput", "placeholder", text.chat.inputPlaceholder);
    setText("#wikiAskBtn", text.chat.send);
    setAllText(".source-pane > h2", [text.chat.references, text.chat.scope]);
    setLabelTexts(".source-pane .radio-card", [text.chat.all, text.chat.recent, text.chat.profile]);

    setText(".settings-model .setting-card-head h2", text.settings.model);
    if ($("envSettingsForm")?.classList.contains("empty")) $("envSettingsForm").textContent = text.settings.envEmpty;
    setLabelTexts(".settings-model .setting-inline-grid label", [text.settings.concurrency, text.settings.fallbackModel]);
    setText("#testLlmBtn", text.settings.testLlm);
    setText("#testEmbedBtn", text.settings.testEmbedding);
    setText("#saveSettingsBtn", text.settings.save);
    if ($("providerTestOutput")?.classList.contains("empty")) $("providerTestOutput").textContent = text.settings.providerTestEmpty;
    setText(".settings-source .setting-card-head h2", text.settings.source);
    const arxivHint = document.querySelector("#settingEnableArxiv")?.closest("label")?.querySelector("em");
    if (arxivHint) arxivHint.textContent = text.settings.arxivPublic;
    setText("#semanticScholarAuthStatus", text.settings.semanticOptional);
    setText("#openReviewAuthStatus", text.settings.openReviewPublic);
    const customRss = document.querySelector("#settingEnableCustomRss")?.closest("label")?.querySelector("strong");
    const customRssHint = document.querySelector("#settingEnableCustomRss")?.closest("label")?.querySelector("em");
    if (customRss) customRss.textContent = text.settings.customRss;
    if (customRssHint) customRssHint.textContent = text.settings.customRssHint;
    setAllText(".source-setting-row > span", [text.settings.arxivCategories, text.settings.conferenceSources]);
    if ($("settingConferenceList")?.classList.contains("empty")) $("settingConferenceList").textContent = text.settings.loadingConferenceSources;
    setText(".source-auth-head strong", text.settings.accessMode);
    setText("#conferenceAuthStatus", text.settings.publicFirst);
    setAllText(".source-mode-grid strong", [text.settings.publicAggregate, text.settings.localCredential, text.settings.manualSupplement]);
    setAllText(".source-mode-grid em", [text.settings.publicAggregateHint, text.settings.localCredentialHint, text.settings.manualSupplementHint]);
    setAttr("#semanticScholarApiKey", "placeholder", text.settings.semanticPlaceholder);
    setLabelTexts(".source-auth-fields label", text.settings.sourceFieldLabels);
    setAttr("#openReviewUsername", "placeholder", text.settings.openReviewPlaceholder);
    setAttr("#openReviewToken", "placeholder", text.settings.tokenPlaceholder);
    setAttr("#conferenceCookieFile", "placeholder", text.settings.cookiePlaceholder);
    setText(".source-auth-note", text.settings.sourceAuthNote);
    setText("#addSourceUrlBtn", text.settings.addUrl);
    if (state.settings) {
      const sourcePrefs = state.settings.source_preferences || {};
      renderConferenceSettings(sourcePrefs);
      updateSourceAuthStatus(sourcePrefs, envMap(state.settings));
    }
    setText(".settings-profile .setting-card-head h2", text.settings.profile);
    setText("#profileSyncStatus", text.settings.profileSync);
    setAttr("#profileUserId", "placeholder", text.settings.userPlaceholder);
    setAttr("#homepageUrl", "placeholder", text.settings.homepagePlaceholder);
    setAttr("#pdfPaths", "placeholder", text.settings.pdfPlaceholder);
    const resetProfileLabel = document.querySelector("#resetProfile")?.parentElement;
    if (resetProfileLabel) resetProfileLabel.lastChild.textContent = ` ${text.settings.resetProfile}`;
    setText("#saveProfileBtn", text.settings.saveProfile);
    setText(".settings-report .setting-card-head h2", text.settings.reportWiki);
    setAllText(".preference-tabs button", [text.settings.standard, text.settings.deep, text.settings.brief]);
    setLabelTexts(".preference-grid .checkline", [
      text.settings.directFeishu,
      text.settings.batchFeishu,
      text.settings.pdfFeishu,
      text.settings.wikiAuto,
      text.settings.notesGitReview
    ]);
    setText(".settings-storage .setting-card-head h2", text.settings.storage);
    setAllText(".storage-counters span", [text.settings.papers, text.settings.queue, "Wiki", text.settings.cache]);
    if ($("settingsList")?.classList.contains("empty")) $("settingsList").textContent = text.settings.storageEmpty;
    setText("#saveStorageSettingsBtn", text.settings.save);
    setText("#exportMarkdownBtn", text.settings.exportMarkdown);
    setText("#exportZipBtn", text.settings.exportZip);
    setText(".settings-advanced .setting-card-head h2", text.settings.advanced);
    setLabelTexts(".settings-advanced .advanced-row", [text.settings.dailyLimit, text.settings.relevance, "HTTP Proxy"]);
    setText("#saveAdvancedSettingsBtn", text.settings.save);

    updatePageTitle();
    syncDateControls();
    updateSelectionSummary();
    if (state.reports.length) renderReportList(state.reports, state.currentReport?.report_id || "");
    if (state.wikiView === "graph" && ($("wikiGraph")?.querySelector(".graph-canvas") || state.wikiGraph || state.wikiNodes.length)) renderWikiGraph();
    if (state.wikiView === "list" && $("wikiGraph")?.querySelector(".wiki-list-view")) renderWikiList();
    if (state.currentWikiEntry) {
      setWikiEntry(
        state.currentWikiEntry.title,
        state.currentWikiEntry.body,
        state.currentWikiEntry.nodeId,
        { editNodeId: state.currentWikiEntry.editNodeId, renderRelations: false }
      );
    }
    if (state.currentWikiNodeId) renderWikiRelations(state.currentWikiNodeId);
    if (state.chatHistoryLoaded) renderChatHistory({ sessions: state.chatHistory, groups: state.chatHistoryGroups });
    if (state.chatMessages?.length) renderChatMessages(state.chatMessages);
    else if (state.currentView === "chat") resetChatThread();
  }

  function setLocale(locale) {
    if (!supportedLocales.has(locale) || state.locale === locale) return;
    const profileDraft = captureProfileDraft();
    state.locale = locale;
    window.localStorage.setItem(LOCALE_KEY, state.locale);
    applyLocale();
    if (state.currentProfile) {
      renderProfileForm(state.currentProfile);
      restoreProfileDraft(profileDraft);
    }
  }

  function captureProfileDraft() {
    const ids = [
      "profileUserId",
      "scholarUrl",
      "homepageUrl",
      "pdfPaths",
      "profileDirectionsInput",
      "profileKeywordsInput",
      "profileAuthorsInput",
      "profileInstitutionsInput",
      "profileTopicsInput"
    ];
    const draft = {};
    ids.forEach((id) => {
      if ($(id)) draft[id] = $(id).value;
    });
    if ($("resetProfile")) draft.resetProfile = $("resetProfile").checked;
    return draft;
  }

  function restoreProfileDraft(draft = {}) {
    Object.entries(draft).forEach(([id, value]) => {
      if (id === "resetProfile") return;
      if ($(id)) $(id).value = value;
    });
    if ($("resetProfile") && Object.prototype.hasOwnProperty.call(draft, "resetProfile")) {
      $("resetProfile").checked = Boolean(draft.resetProfile);
    }
  }

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
      runButton.textContent = ui().papers.backgroundRunning;
      return;
    }
    const today = todayDateValue();
    if (!dateInput.value) dateInput.value = today;
    if (dateInput.value > today) dateInput.value = today;
    daysInput.value = String(selectedDateFetchDays());
    runButton.disabled = false;
    runButton.textContent = dateInput.value === today ? ui().papers.pullToday : ui().papers.pullSelected;
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
    $("statusText").textContent = statusText(message);
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
    feedbackButton.textContent = busy && !generateReports ? ui().papers.submitting : ui().papers.submitFeedback;
    readButton.textContent = busy && generateReports ? ui().papers.generating : ui().papers.submitAndRead;
  }

  function directReadElements(kind) {
    return {
      button: $(kind === "pdf" ? "readPdfBtn" : "readArxivBtn"),
      status: $(kind === "pdf" ? "directPdfStatus" : "directArxivStatus")
    };
  }

  function setDirectReadStatus(kind, type, title, detail = "") {
    const { status } = directReadElements(kind);
    if (!status) return;
    status.className = `direct-read-status ${type || "success"}`;
    status.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    `;
    status.hidden = false;
  }

  function setDirectReadBusy(kind, busy) {
    const { button } = directReadElements(kind);
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("loading", busy);
    button.textContent = busy ? ui().papers.generating : ui().reports.generate;
  }

  function flashButtonFeedback(button, type = "click") {
    if (!button || (button.disabled && type === "click")) return;
    const previousTimer = state.buttonFeedbackTimers.get(button);
    if (previousTimer) window.clearTimeout(previousTimer);
    button.classList.remove("feedback-click", "feedback-success", "feedback-error");
    button.classList.add(`feedback-${type}`);
    const timer = window.setTimeout(() => {
      button.classList.remove("feedback-click", "feedback-success", "feedback-error");
      state.buttonFeedbackTimers.delete(button);
    }, type === "click" ? 520 : 760);
    state.buttonFeedbackTimers.set(button, timer);
  }

  function setActionButtonBusy(button, busy) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.wasDisabled) button.dataset.wasDisabled = button.disabled ? "true" : "false";
      button.classList.add("is-busy");
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      return;
    }
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    if (button.dataset.wasDisabled) {
      button.disabled = button.dataset.wasDisabled === "true";
      delete button.dataset.wasDisabled;
    }
  }

  function bindButtonFeedback() {
    document.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      state.lastActionButton = button;
      flashButtonFeedback(button, "click");
      window.setTimeout(() => {
        if (state.lastActionButton === button) state.lastActionButton = null;
      }, 0);
    }, true);
  }

  function responseLanguage() {
    return state.locale === "en" ? "en" : "zh";
  }

  async function runAction(action, busyText = ui().status.busy, options = {}) {
    const actionButton = options.button || state.lastActionButton;
    try {
      setActionButtonBusy(actionButton, true);
      setStatus(busyText);
      await action();
      setStatus(ui().status.ready);
      flashButtonFeedback(actionButton, "success");
    } catch (error) {
      setStatus(ui().status.error);
      console.error(error);
      flashButtonFeedback(actionButton, "error");
      if (!error.paperflowToastShown) showFeedbackToast("error", ui().common.operationFailed, error.message || String(error));
    } finally {
      setActionButtonBusy(actionButton, false);
    }
  }

  async function api(path, options = {}) {
    if (DEMO_MODE) return demoApi(path, options);
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options
    });
    const data = await response.json();
    if (!data.ok) {
      const error = new Error(data.error || ui().common.requestFailed);
      error.status = response.status;
      error.path = path;
      error.payload = data;
      throw error;
    }
    return data;
  }

  function isUnknownApiRoute(error, route = "") {
    return Number(error?.status) === 404
      && String(error?.message || "").includes("Unknown API route")
      && (!route || String(error?.path || "").includes(route));
  }

  async function demoApi(path, options = {}) {
    await new Promise((resolve) => window.setTimeout(resolve, 90));
    const url = new URL(path, window.location.origin);
    const route = url.pathname;
    const method = (options.method || "GET").toUpperCase();
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
              title: body.arxiv_id
                ? (responseLanguage() === "en" ? `arXiv ${body.arxiv_id} Reading Report` : `arXiv ${body.arxiv_id} 精读报告`)
                : "Efficient Test-Time Scaling for Reasoning Agents",
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
    if (route === "/api/chat/sessions") {
      const grouped = {};
      demoChatSessions.forEach((session) => {
        const dateKey = String(session.updated_at || session.created_at || todayDateValue()).slice(0, 10);
        if (!grouped[dateKey]) grouped[dateKey] = [];
        grouped[dateKey].push(session);
      });
      return {
        ok: true,
        sessions: demoChatSessions,
        groups: Object.keys(grouped).map((date) => ({ date, sessions: grouped[date] }))
      };
    }
    if (route === "/api/chat/session" && method === "POST") {
      const now = new Date().toISOString().slice(0, 19).replace("T", " ");
      const session = {
        session_id: `demo_chat_${Date.now()}`,
        user_id: body.user_id || "user_demo",
        title: body.title || ui().chat.newChatTitle,
        created_at: now,
        updated_at: now,
        message_count: 0
      };
      demoChatSessions.unshift(session);
      demoChatMessages[session.session_id] = [];
      return { ok: true, session };
    }
    if (route === "/api/chat/session") {
      const sessionId = url.searchParams.get("session_id") || "";
      const session = demoChatSessions.find((item) => item.session_id === sessionId);
      return { ok: true, session, messages: demoChatMessages[sessionId] || [] };
    }
    if (route === "/api/chat/session/delete") {
      const sessionId = body.session_id || "";
      const index = demoChatSessions.findIndex((item) => item.session_id === sessionId);
      if (index >= 0) demoChatSessions.splice(index, 1);
      delete demoChatMessages[sessionId];
      return { ok: true, deleted: index >= 0 };
    }
    if (route === "/api/wiki/ask") {
      const now = new Date().toISOString().slice(0, 19).replace("T", " ");
      let sessionId = body.session_id || "";
      let session = demoChatSessions.find((item) => item.session_id === sessionId);
      if (!session) {
        sessionId = sessionId || `demo_chat_${Date.now()}`;
        session = {
          session_id: sessionId,
          user_id: body.user_id || "user_demo",
          title: String(body.question || ui().chat.newChatTitle).slice(0, 48),
          created_at: now,
          updated_at: now,
          message_count: 0
        };
        demoChatSessions.unshift(session);
        demoChatMessages[sessionId] = [];
      }
      const answer = {
        ok: true,
        text: responseLanguage() === "en"
          ? "Based on the latest 5 papers and 3 Wiki entries, the RAG direction is shifting from plain retrieval toward structured memory, traceable citations, and multimodal evidence fusion.[1][2] Prioritize deep reads on test-time scaling and structured memory.[3]"
          : "基于最近的 5 篇论文和 3 个 Wiki 条目，RAG 方向的重点正在从单纯检索转向结构化记忆、引用可追溯和多模态证据融合。[1][2] 建议优先精读 test-time scaling 与 structured memory 两条线索。[3]",
        mode: "wiki",
        retrieval_required: true,
        routing_reason: body.mentions?.length ? "explicit_mention" : "local_research_context",
        citations: demoSources,
        sources: demoSources,
        mentions: body.mentions || [],
        streaming: { provider: false, transport: "desktop-progressive" },
        session_id: sessionId
      };
      const messages = demoChatMessages[sessionId] || [];
      messages.push({
        id: messages.length + 1,
        session_id: sessionId,
        user_id: session.user_id,
        role: "user",
        content: body.question || "",
        metadata: { scope: body.scope || "all", mentions: body.mentions || [] },
        created_at: now
      });
      messages.push({
        id: messages.length + 1,
        session_id: sessionId,
        user_id: session.user_id,
        role: "assistant",
        content: answer.text,
        metadata: { ...answer },
        created_at: now
      });
      demoChatMessages[sessionId] = messages;
      session.updated_at = now;
      session.message_count = messages.length;
      return answer;
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
      return { ok: true, kind: body.kind || "llm", provider: "demo", message: responseLanguage() === "en" ? "Connection test passed (demo mode)" : "连接测试通过（demo 模式）" };
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
    state.currentView = name;
    document.body.classList.toggle("chat-view", name === "chat");
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === name));
    document.querySelectorAll(".rail-item").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
    const active = $(name);
    if (active) {
      updatePageTitle();
    }
    if (updateHash && window.location.hash.slice(1) !== name) {
      history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${name}`);
    }
    window.scrollTo({ top: 0, left: 0 });
    if (name === "reports" && !options.skipLoad) runAction(() => refreshReports({ keepSelection: true }), "加载报告");
    if (name === "wiki" && !options.skipLoad) runAction(loadWiki, "加载 Wiki");
    if (name === "chat" && !options.skipLoad) runAction(() => loadChatSessions({ openLatest: true }), "加载历史对话");
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
    const label = userId ? `${role}${userId}` : ui().common.untitledUser;
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
    $("healthText").textContent = DEMO_MODE ? ui().health.demo : data.database_exists ? ui().health.ready : ui().health.init;
  }

  function defaultCheckedForSource(index, mode = "none") {
    if (mode === "all") return true;
    if (mode === "first3") return index < 3;
    return false;
  }

  function renderChoiceList(id, items, options = {}) {
    const target = $(id);
    target.className = "choice-list";
    const defaultChecked = options.defaultChecked || "none";
    target.innerHTML = items.map((item, index) => {
      const value = item.id || item.name || item;
      const label = item.name || item.id || item;
      const checked = defaultCheckedForSource(index, defaultChecked) ? "checked" : "";
      return `<label class="source-choice"><input type="checkbox" value="${escapeHtml(value)}" ${checked}>${escapeHtml(label)}</label>`;
    }).join("");
  }

  async function loadSourceOptions() {
    if (state.sourceOptionsLoaded) return;
    const data = await api("/api/source-options");
    state.sourceOptions = data;
    renderChoiceList("arxivCategories", data.arxiv_categories || [], { defaultChecked: "all" });
    renderChoiceList("conferenceSources", data.conferences || [], { defaultChecked: "none" });
    renderChoiceList("journalSources", data.journals || [], { defaultChecked: "none" });
    state.sourceOptionsLoaded = true;
  }

  function selectedSourceValues(id) {
    return Array.from($(id).querySelectorAll("input:checked")).map((input) => input.value);
  }

  function selectedSettingTagValues(id) {
    return Array.from($(id)?.querySelectorAll("span") || [])
      .map((item) => item.textContent.trim())
      .filter((value) => value && ![i18n.zh.common.notConfigured, i18n.en.common.notConfigured, i18n.zh.settings.placeholderMissing, i18n.en.settings.placeholderMissing].includes(value));
  }

  function syncChoiceListFromSettings(id, values, enabled = true, options = {}) {
    const target = $(id);
    if (!target) return;
    const configured = new Set(splitListValue(values));
    const inputs = Array.from(target.querySelectorAll("input[type='checkbox']"));
    const defaultChecked = options.defaultChecked || "none";
    const useConfigured = options.useConfigured !== false;
    inputs.forEach((input, index) => {
      if (useConfigured && configured.size) {
        input.checked = configured.has(input.value);
      } else {
        input.checked = defaultCheckedForSource(index, defaultChecked);
      }
      input.disabled = !enabled;
      input.closest("label")?.classList.toggle("disabled", !enabled);
    });
  }

  function syncDailySourceControls(sourcePrefs = {}) {
    syncChoiceListFromSettings(
      "arxivCategories",
      [],
      sourcePrefs.enable_arxiv !== false,
      { defaultChecked: "all", useConfigured: false }
    );
    syncChoiceListFromSettings(
      "conferenceSources",
      [],
      sourcePrefs.enable_openreview !== false,
      { defaultChecked: "none", useConfigured: false }
    );
    syncChoiceListFromSettings(
      "journalSources",
      [],
      true,
      { defaultChecked: "none", useConfigured: false }
    );
  }

  function configuredDailyLimit() {
    const value = Number($("dailyLimitInput")?.value || state.settings?.advanced?.daily_limit || 30);
    if (!Number.isFinite(value)) return 30;
    return Math.max(1, Math.min(500, Math.round(value)));
  }

  function collectDailyOptions() {
    const sourcePrefs = state.settings?.source_preferences || {};
    const arxivEnabled = $("settingEnableArxiv") ? $("settingEnableArxiv").checked : sourcePrefs.enable_arxiv !== false;
    const openReviewEnabled = $("settingEnableOpenReview") ? $("settingEnableOpenReview").checked : sourcePrefs.enable_openreview !== false;
    const arxivCategories = arxivEnabled ? selectedSourceValues("arxivCategories") : [];
    const conferences = openReviewEnabled ? selectedSourceValues("conferenceSources") : [];
    return {
      arxiv_categories: arxivCategories,
      conferences,
      journals: selectedSourceValues("journalSources")
    };
  }

  function paperReportKey(number, pushId = state.push?.push_id) {
    return [currentUser(), pushId || "no-push", Number(number)].join("::");
  }

  async function ensureLlmReadyForReading() {
    try {
      const data = await api("/api/provider-test", {
        method: "POST",
        body: JSON.stringify({ kind: "llm" })
      });
      const provider = String(data.provider || "").toLowerCase();
      const model = data.model || ui().papers.llmUnknownModel;
      if (!provider || provider === "mock") {
        const detail = ui().papers.llmNotReadyDetail;
        showPaperFeedback("warning", ui().papers.llmNotReadyTitle, detail);
        showFeedbackToast("warning", ui().papers.llmNotReadyTitle, detail);
        return false;
      }
      if (data.ok === false) {
        const detail = data.error || ui().papers.llmSmokeFailedDetail;
        showPaperFeedback("warning", ui().papers.llmSmokeFailedTitle, detail);
        showFeedbackToast("warning", ui().papers.llmSmokeFailedTitle, detail);
        return false;
      }
      console.info(`PaperFlow LLM preflight ok: ${provider}:${model}`);
      return true;
    } catch (error) {
      const detail = error.message || String(error);
      showPaperFeedback("warning", ui().papers.llmUnavailableTitle, ui().papers.llmUnavailableDetail(detail));
      showFeedbackToast("warning", ui().papers.llmUnavailableTitle, detail);
      return false;
    }
  }

  function pushMetaText(push, papers, metadata = {}, options = {}) {
    if (!push?.push_id) return ui().papers.pushEmpty;
    const parts = [];
    if (options.fromCache) parts.push(ui().papers.recentCache);
    parts.push(`${ui().papers.batch} ${push.push_id}`);
    parts.push(push.push_time || ui().common.localTime);
    parts.push(ui().papers.recommendations(papers.length));
    if (metadata.daily_limit) parts.push(ui().papers.dailyLimit(metadata.daily_limit));
    if (metadata.limit_per_source) parts.push(ui().papers.perSourceLimit(metadata.limit_per_source));
    if (metadata.relevance_threshold) parts.push(ui().papers.threshold(metadata.relevance_threshold));
    const sourceParts = [
      metadata.arxiv_categories?.length ? `arXiv ${metadata.arxiv_categories.length}` : "",
      metadata.conferences?.length ? ui().papers.conferenceCount(metadata.conferences.length) : "",
      metadata.journals?.length ? ui().papers.journalCount(metadata.journals.length) : "",
      metadata.enable_semantic_scholar ? "Semantic Scholar" : "",
      metadata.enable_custom_rss ? "RSS" : ""
    ].filter(Boolean);
    if (sourceParts.length) parts.push(ui().papers.sourceCounts(sourceParts));
    return parts.join(" · ");
  }

  function renderPush(push, options = {}) {
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
    $("pushMeta").textContent = pushMetaText(push, papers, metadata, options);
    if (!papers.length) {
      $("paperList").className = "paper-list empty";
      $("paperList").textContent = ui().papers.noRecommendations;
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
      const tags = paper.tags || [paper.source || ui().papers.sourceFallback, ui().papers.profileMatch];
      return `
        <article class="paper-card" data-paper-number="${number}">
          <div class="score-ring" style="--score: ${Math.min(score, 100)}%">${score}%</div>
          <div class="paper-content">
            <h3>${escapeHtml(paper.title || "Untitled Paper")}</h3>
            <p class="paper-authors">${escapeHtml(Array.isArray(paper.authors) ? paper.authors.join(", ") : (paper.authors || paper.author || ui().papers.authorPending))}</p>
            <p class="paper-abstract">${escapeHtml(paper.abstract || paper.summary || "")}</p>
            <div class="paper-tags">
              ${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
            </div>
          </div>
          <div class="paper-actions">
            <button data-action="read" data-number="${number}" class="${reportId ? "ready" : ""} ${isReading ? "loading" : ""}" type="button" ${isReading ? "disabled" : ""}>${isReading ? ui().papers.loading : reportId ? ui().papers.readReport : ui().papers.read}</button>
            <button data-action="skip" data-number="${number}" type="button">${ui().papers.skip}</button>
            <button data-action="later" data-number="${number}" type="button">${ui().papers.later}</button>
          </div>
        </article>`;
    }).join("");
    updateSelectionSummary();
  }

  async function loadLatestPush() {
    const data = await api(`/api/latest-push?user_id=${encodeURIComponent(currentUser())}`);
    renderPush(data.push || data.result?.push || data, { fromCache: true });
  }

  async function runDaily() {
    syncDateControls();
    if (state.dailyPolling && state.dailyTaskId) {
      showFeedbackToast("success", ui().papers.stillRunningTitle, ui().papers.stillRunningDetail(state.dailyTaskId));
      return;
    }
    const days = selectedDateFetchDays();
    $("daysInput").value = String(days);
    const options = collectDailyOptions();
    const userId = currentUser();
    const runButton = $("runDailyBtn");
    runButton.disabled = true;
    runButton.textContent = ui().papers.checkingCache;
    const pollToken = ++state.dailyPollToken;
    try {
      const data = await api("/api/daily/start", {
        method: "POST",
        body: JSON.stringify({ user_id: userId, days, target_date: $("paperDate").value, limit_per_source: configuredDailyLimit(), ...options })
      });
      const taskId = data.task?.task_id || "";
      if (data.cached || data.task?.status === "completed") {
        if (data.task?.push) renderPush(data.task.push, { fromCache: Boolean(data.cached || data.task.cached) });
        if (data.cached) showFeedbackToast("success", ui().papers.loadedCacheTitle, ui().papers.loadedCacheDetail);
        await loadWiki();
        return;
      }
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
    $("pushMeta").textContent = ui().papers.taskStatus(task);
    $("paperList").className = "paper-list empty syncing";
    $("paperList").textContent = ui().papers.taskPending;
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
        throw new Error(task.error || ui().papers.pullFailed);
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
      showFeedbackToast("error", ui().papers.pullFailed, error.message || String(error));
    }).finally(() => {
      if (pollToken === state.dailyPollToken) setDailyTaskState("", "", false);
    });
  }

  function updateSelectionSummary() {
    $("selectedStat").textContent = state.selected.size;
    $("readingQueueStat").textContent = state.selected.size;
    $("selectionSummary").textContent = ui().papers.selectionSummary(state.selected.size, state.skipped.size, state.later.size);
    document.querySelectorAll(".paper-card").forEach((card) => {
      const number = Number(card.dataset.paperNumber);
      const disposition = state.selected.has(number)
        ? "read"
        : state.skipped.has(number)
          ? "skip"
          : state.later.has(number)
            ? "later"
            : "";
      if (disposition) {
        card.dataset.disposition = disposition;
      } else {
        delete card.dataset.disposition;
      }
      card.querySelectorAll(".paper-actions button").forEach((button) => {
        button.classList.toggle("active", button.dataset.action === disposition);
      });
      const skipButton = card.querySelector('.paper-actions button[data-action="skip"]');
      const laterButton = card.querySelector('.paper-actions button[data-action="later"]');
      if (skipButton) skipButton.textContent = disposition === "skip" ? ui().papers.skipped : ui().papers.skip;
      if (laterButton) laterButton.textContent = disposition === "later" ? ui().papers.laterAdded : ui().papers.later;
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
      button.textContent = isReading ? ui().papers.loading : reportId ? ui().papers.readReport : state.selected.has(number) ? ui().papers.readSelected : ui().papers.read;
      button.classList.toggle("loading", isReading);
      button.classList.toggle("ready", Boolean(reportId) && !isReading);
    });
  }

  function setPaperDisposition(number, action) {
    const isSelected = action === "read" && state.selected.has(number);
    const isSkipped = action === "skip" && state.skipped.has(number);
    const isLater = action === "later" && state.later.has(number);
    const alreadyActive = isSelected || isSkipped || isLater;

    state.selected.delete(number);
    state.skipped.delete(number);
    state.later.delete(number);

    if (!alreadyActive) {
      if (action === "read") state.selected.add(number);
      if (action === "skip") state.skipped.add(number);
      if (action === "later") state.later.add(number);
    }

    updateSelectionSummary();
    if (alreadyActive) {
      showPaperFeedback("success", ui().papers.cancelled, ui().papers.restored(number));
      return;
    }
    const labels = ui().papers.dispositionLabels;
    showPaperFeedback(
      "success",
      ui().papers.markedAs(labels[action]),
      ui().papers.dispositionHelp
    );
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
        title: ui().papers.emptyFeedbackTitle,
        detail: ui().papers.emptyFeedbackDetail
      };
    }

    const title = generateReports
      ? reportCount
        ? ui().papers.submittedWithReports(reportCount)
        : ui().papers.submittedNoReport
      : ui().papers.submitted;
    const detailParts = [];
    if (totalFeedback) {
      detailParts.push(ui().papers.feedbackCounts(selectedCount, skippedCount, laterCount));
      detailParts.push(ui().papers.profileWikiUpdated);
    }
    if (wikiBackfilled) detailParts.push(ui().papers.wikiBackfilled(wikiBackfilled));
    if (feishuWarning) detailParts.push(feishuWarning);
    if (!detailParts.length && reportCount) detailParts.push(ui().papers.reportEntered);
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
    if (!state.push?.push_id) throw new Error(ui().papers.loadPushFirst);
    const reportKey = paperReportKey(number);
    const existingReportId = state.paperReports.get(reportKey);
    if (existingReportId) {
      await openReport(existingReportId);
      return;
    }
    setPaperDisposition(number, "read");
  }

  async function submitFeedback(generateReports) {
    if (!state.push?.push_id) {
      showPaperFeedback("error", ui().papers.submitUnavailableTitle, ui().papers.submitUnavailableDetail);
      throw new Error(ui().papers.loadPushFirst);
    }
    const selectedNumbers = Array.from(state.selected);
    if (generateReports && !selectedNumbers.length) {
      showPaperFeedback("warning", ui().papers.chooseReadTitle, ui().papers.chooseReadDetail);
      showFeedbackToast("warning", ui().papers.chooseReadTitle, ui().papers.chooseReadToast);
      return;
    }
    if (generateReports && !(await ensureLlmReadyForReading())) {
      return;
    }
    const endpoint = generateReports ? "/api/submit" : "/api/feedback";
    const readingKeys = generateReports ? selectedNumbers.map((number) => paperReportKey(number)) : [];
    setSubmitButtonsBusy(true, generateReports);
    readingKeys.forEach((key) => state.paperReading.add(key));
    updateSelectionSummary();
    showPaperFeedback(
      "pending",
      generateReports ? ui().papers.submittingReportTitle : ui().papers.submittingFeedbackTitle,
      ui().papers.submittingDetail
    );
    try {
      const data = await api(endpoint, {
        method: "POST",
        body: JSON.stringify({
          user_id: currentUser(),
          push_id: state.push.push_id,
          selected_numbers: selectedNumbers,
          skipped_numbers: Array.from(state.skipped),
          later_numbers: Array.from(state.later),
          generate_reports: generateReports,
          write_feishu: $("writeFeishuReports")?.checked || false,
          response_language: responseLanguage()
        })
      });
      if (generateReports) {
        (data.reports?.created_docs || []).forEach((doc, index) => {
          const number = selectedNumbers[index];
          if (number && doc?.report_id) state.paperReports.set(paperReportKey(number), doc.report_id);
        });
      }
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
      showPaperFeedback("error", ui().papers.submitFailed, error.message || String(error));
      throw error;
    } finally {
      readingKeys.forEach((key) => state.paperReading.delete(key));
      updateSelectionSummary();
      setSubmitButtonsBusy(false, generateReports);
    }
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

    const renderInlineMarkdown = (text) => {
      let html = escapeHtml(text || "");
      html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noreferrer">$2</a>');
      return html;
    };
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
      out.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
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

  function reportAnnotationKey(reportId) {
    return `paperflow.report.annotations.${reportId || ""}`;
  }

  function loadReportAnnotation(reportId) {
    if (!reportId) return "";
    try {
      return window.localStorage.getItem(reportAnnotationKey(reportId)) || "";
    } catch (error) {
      return "";
    }
  }

  function saveReportAnnotation() {
    const reportId = state.currentReport?.report_id;
    const body = $("reportViewerBody");
    if (!reportId || !body || body.classList.contains("empty")) return;
    try {
      window.localStorage.setItem(reportAnnotationKey(reportId), body.innerHTML);
      $("clearReportAnnotationsBtn").disabled = false;
    } catch (error) {
      console.warn("Unable to save report annotation", error);
    }
  }

  function hideReportAnnotationToolbar() {
    const toolbar = document.querySelector(".annotation-toolbar");
    if (!toolbar) return;
    toolbar.classList.remove("visible");
  }

  function updateReportAnnotationToolbar() {
    const toolbar = document.querySelector(".annotation-toolbar");
    const body = $("reportViewerBody");
    const selection = window.getSelection();
    if (!toolbar || !body || body.classList.contains("empty") || !selection || selection.rangeCount === 0 || selection.isCollapsed) {
      hideReportAnnotationToolbar();
      return;
    }
    const range = selection.getRangeAt(0);
    if (!body.contains(range.commonAncestorContainer)) {
      hideReportAnnotationToolbar();
      return;
    }
    state.reportAnnotationRange = range.cloneRange();
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      hideReportAnnotationToolbar();
      return;
    }
    toolbar.classList.add("visible");
    const toolbarRect = toolbar.getBoundingClientRect();
    const left = Math.max(8, Math.min(window.innerWidth - toolbarRect.width - 8, rect.left + rect.width / 2 - toolbarRect.width / 2));
    const top = Math.max(8, rect.top - toolbarRect.height - 8);
    toolbar.style.left = `${left}px`;
    toolbar.style.top = `${top}px`;
  }

  function selectedReportAnnotationRange() {
    const body = $("reportViewerBody");
    const selection = window.getSelection();
    if (body && selection && selection.rangeCount > 0 && !selection.isCollapsed) {
      const range = selection.getRangeAt(0);
      if (body.contains(range.commonAncestorContainer)) {
        return range.cloneRange();
      }
    }
    const saved = state.reportAnnotationRange;
    if (body && saved && body.contains(saved.commonAncestorContainer)) {
      return saved.cloneRange();
    }
    return null;
  }

  function applyReportAnnotation(command, value) {
    const body = $("reportViewerBody");
    const range = selectedReportAnnotationRange();
    if (!body || !range || range.collapsed || !body.contains(range.commonAncestorContainer)) return;
    const wrapper = document.createElement("span");
    wrapper.dataset.paperflowAnnotation = command;
    if (command === "foreColor") wrapper.style.color = value;
    else if (command === "bold") wrapper.style.fontWeight = "700";
    else if (command === "italic") wrapper.style.fontStyle = "italic";
    else wrapper.style.backgroundColor = value;
    wrapper.appendChild(range.extractContents());
    range.insertNode(wrapper);
    saveReportAnnotation();
    const selection = window.getSelection();
    selection?.removeAllRanges();
    state.reportAnnotationRange = null;
    hideReportAnnotationToolbar();
  }

  function clearReportAnnotations() {
    if (!state.currentReport?.report_id) return;
    try {
      window.localStorage.removeItem(reportAnnotationKey(state.currentReport.report_id));
    } catch (error) {
      console.warn("Unable to clear report annotation", error);
    }
    $("reportViewerBody").innerHTML = renderMarkdown(state.currentReport.markdown || "");
    $("clearReportAnnotationsBtn").disabled = true;
    hideReportAnnotationToolbar();
  }

  function renderReportList(reports, activeId = "") {
    const target = $("reportsList");
    if (!reports.length) {
      target.className = "reports-list empty";
      target.textContent = ui().reports.none;
      return;
    }
    target.className = "reports-list";
    target.innerHTML = reports.map((report) => `
      <button class="report-row ${report.report_id === activeId ? "active" : ""}" data-report-id="${escapeHtml(report.report_id)}" type="button">
        <h3>${escapeHtml(report.title || ui().reports.defaultTitle)}</h3>
        <p>${escapeHtml(report.saved_at || "")} · ${escapeHtml(report.status || ui().reports.completed)}</p>
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
    const count = data.count || state.reports.length;
    $("reportSources").textContent = (data.source_dirs || []).length
      ? ui().reports.directory(data.source_dirs || [], count)
      : ui().reports.count(count);
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
      if (!silent) throw new Error(ui().reports.missing);
      return;
    }
    state.currentReport = report;
    renderReportList(state.reports, report.report_id);
    $("reportViewerTitle").textContent = report.title || ui().reports.defaultTitle;
    $("reportViewerMeta").textContent = [report.user_id, report.saved_at, report.report_path].filter(Boolean).join(" · ");
    $("reportViewerBody").className = "markdown-body";
    const annotatedHtml = loadReportAnnotation(report.report_id);
    $("reportViewerBody").innerHTML = annotatedHtml || renderMarkdown(report.markdown || "");
    $("clearReportAnnotationsBtn").disabled = !annotatedHtml;
    hideReportAnnotationToolbar();
    setReportLinks(report);
  }

  async function directRead(kind) {
    const isPdf = kind === "pdf";
    const sourceLabel = isPdf ? ui().common.localPdf : ui().common.arxiv;
    const payload = {
      user_id: currentUser(),
      write_feishu: isPdf ? Boolean($("directPdfWriteFeishu")?.checked) : Boolean($("directWriteFeishu")?.checked)
    };
    let route = "/api/read/arxiv";
    if (!isPdf) {
      const raw = $("directArxivId").value.trim();
      payload.arxiv_id = raw.replace(/^https?:\/\/arxiv\.org\/abs\//, "");
      if (!payload.arxiv_id) {
        setDirectReadStatus("arxiv", "warning", ui().reports.arxivRequiredTitle, ui().reports.arxivRequiredDetail);
        throw new Error(ui().reports.arxivRequiredTitle);
      }
    } else {
      route = "/api/read/pdf";
      payload.pdf_path = $("directPdfPath").value.trim();
      payload.title = $("directPdfTitle").value.trim();
      if (!payload.pdf_path) {
        setDirectReadStatus("pdf", "warning", ui().reports.pdfRequiredTitle, ui().reports.pdfRequiredDetail);
        throw new Error(ui().reports.pdfRequiredTitle);
      }
    }
    payload.response_language = responseLanguage();
    setDirectReadBusy(kind, true);
    setDirectReadStatus(
      kind,
      "pending",
      ui().reports.generatingTitle(sourceLabel),
      ui().reports.generatingDetail
    );
    try {
      const data = await api(route, { method: "POST", body: JSON.stringify(payload) });
      const reports = data.reports || data;
      const doc = reports?.created_docs?.[0];
      if (!doc?.report_id) {
        throw new Error(ui().reports.missingReportId);
      }
      const reportTitle = doc.title || doc.paper?.title || ui().reports.defaultTitle;
      const reportPath = doc.report_path || "";
      const warning = reports.feishu_warning || "";
      setDirectReadStatus(
        kind,
        warning ? "warning" : "success",
        warning ? ui().reports.generatedWarning : ui().reports.generatedTitle,
        `${reportTitle}${reportPath ? ` · ${reportPath}` : ""}${warning ? ` · ${warning}` : ""}`
      );
      showFeedbackToast(warning ? "warning" : "success", ui().reports.generatedToast, reportTitle);
      await openReport(doc.report_id);
      await loadWiki();
    } catch (error) {
      setDirectReadStatus(kind, "error", ui().reports.generationFailed, error.message || String(error));
      throw error;
    } finally {
      setDirectReadBusy(kind, false);
    }
  }

  function graphId(node) {
    const source = node || {};
    return String(source.node_id || source.id || source.title || "node");
  }

  const wikiEnglishTextMap = [
    ["当前用户画像", "Current User Profile"],
    ["用户反馈、精读和跳过记录形成的本地研究状态。", "User feedback, deep-reading records, and skip signals form this local research state."],
    ["知识库架构", "Knowledge Architecture"],
    ["当前主线", "Current Themes"],
    ["证据来源", "Evidence Sources"],
    ["精读论文", "Reading papers"],
    ["章节/方法片段", "Sections / method snippets"],
    ["用户方向节点", "User direction nodes"],
    ["代表论文", "Representative Papers"],
    ["用户方向", "User Direction"],
    ["当前信号", "Current Signals"],
    ["最近证据", "Recent Evidence"],
    ["关联证据", "Related Evidence"],
    ["展示意义", "Why It Helps"],
    ["暂无稳定主题", "No stable themes yet"],
    ["暂无论文证据", "No paper evidence yet"],
    ["暂无直接论文证据", "No direct paper evidence yet"],
    ["暂无精读记录", "No deep-reading records yet"],
    ["暂无稳定信号", "No stable signals yet"],
    ["从全文语义检索命中的片段看", "From full-text semantic retrieval hits"],
    ["该主题页由近期阅读、选择和画像漂移自动生成，用来把分散论文沉淀成可追踪的研究主线。", "This topic page is generated from recent reading, selections, and profile drift so scattered papers can become a traceable research thread."],
    ["该主题页由论文关键词聚合生成，用来把分散的 paper 节点组织成可追踪的研究主线。", "This topic page is generated from paper keyword aggregation so scattered paper nodes can become a traceable research thread."],
    ["暂无直接证据论文", "No direct evidence papers yet"],
    ["暂无贡献摘要", "No contribution summary yet"],
    ["暂无画像相关性说明", "No profile-relevance notes yet"],
    ["暂无总结，建议回到精读报告核对。", "No summary yet; check the reading report."],
    ["待从后续精读中沉淀", "To be distilled from later deep reads"],
    ["精读报告", "Reading Report"],
    ["论文推荐", "Paper Recommendation"],
    ["手动导入", "Manual Import"],
    ["参考文献", "Reference"],
    ["论文/报告", "Paper/Report"],
    ["画像/前沿", "Profile/Frontier"],
    ["主题主线", "Themes"],
    ["方法片段", "Method Snippets"],
    ["论文证据", "Paper Evidence"],
    ["本地 Wiki", "Local Wiki"],
    ["用户画像", "User Profile"],
    ["知识库", "Knowledge Base"],
    ["关联论文", "Related Papers"],
    ["相关概念", "Related Concepts"],
    ["结构化记忆", "Structured Memory"],
    ["知识图谱", "Knowledge Graph"],
    ["检索评估", "Retrieval Evaluation"],
    ["记忆压缩", "Memory Compression"],
    ["引用证据", "Citation Evidence"],
    ["个性化推荐", "Personalized Recommendation"],
    ["多模态协作", "Multimodal Collaboration"],
    ["研究前沿", "Research Frontier"],
    ["论文流", "Paper Flow"],
    ["多模态推理", "Multimodal Reasoning"],
    ["推理泛化", "Reasoning Generalization"],
    ["视觉语言模型", "Vision-Language Models"],
    ["推理效率", "Inference Efficiency"],
    ["蛋白结构检索", "Protein Structure Retrieval"],
    ["基因编辑", "Gene Editing"],
    ["强化学习", "Reinforcement Learning"],
    ["开源模型", "Open-Source Models"],
    ["用户反馈", "User Feedback"],
    ["精读记录", "Deep-reading Records"],
    ["兴趣漂移", "Interest Drift"],
    ["画像漂移", "Profile Drift"],
    ["前沿", "Frontier"],
    ["概念", "Concept"],
    ["方法", "Method"],
    ["主题", "Theme"],
    ["证据", "Evidence"],
    ["引用", "Citation"],
    ["检索", "Retrieval"],
    ["相关", "Related"],
    ["趋势", "Trend"],
    ["动态", "Dynamics"],
    ["增强", "Increased"],
    ["减弱", "Decreased"],
    ["新增", "New"],
    ["稳定", "Stable"]
  ];

  function localizeWikiText(value) {
    let text = String(value ?? "");
    if (state.locale !== "en" || !text) return text;
    wikiEnglishTextMap.forEach(([source, target]) => {
      text = text.replaceAll(source, target);
    });
    return text
      .replace(/Direction:\s*Increased/gi, "Direction: Increased")
      .replace(/Direction:\s*Decreased/gi, "Direction: Decreased")
      .replace(/Direction:\s*New/gi, "Direction: New")
      .replace(/Direction:\s*Stable/gi, "Direction: Stable")
      .replace(/Period:\s*([0-9W-]+)/g, "Period: $1")
      .replace(/Weight:\s*/g, "Weight: ");
  }

  function rawGraphTitle(node) {
    const source = node || {};
    return String(source.title || source.id || source.node_id || ui().wiki.architecture);
  }

  function rawGraphBody(node) {
    const source = node || {};
    return String(source.body || source.snippet || "");
  }

  function graphTitle(node) {
    return localizeWikiText(rawGraphTitle(node));
  }

  function graphBody(node) {
    return localizeWikiText(rawGraphBody(node));
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
    return ui().wiki.typeLabels[type] || ui().wiki.typeLabels.topic;
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
    const normalized = String(title || ui().wiki.architecture).replace(/\s+/g, " ").trim();
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized;
  }

  function nodeSearchText(node) {
    return [rawGraphTitle(node), rawGraphBody(node), node?.keywords, node?.node_type, graphId(node)]
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
      .map((alias) => localizeWikiText(alias.label));
  }

  function candidateLabelsForNode(node) {
    const text = nodeSearchText(node);
    const labels = new Set(aliasLabelsForText(text));
    const tokens = tokenizeKnowledgeText([node?.keywords, rawGraphTitle(node)].filter(Boolean).join(" "));
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
    const joiner = state.locale === "en" ? ", " : "、";
    const themes = entries.slice(0, 5).map((entry) => localizeWikiText(entry.label)).join(joiner) || (state.locale === "en" ? "No stable themes yet" : "暂无稳定主题");
    const papers = topPapers.slice(0, 3).map((paper) => `- ${graphTitle(paper)}`).join("\n") || (state.locale === "en" ? "- No paper evidence yet" : "- 暂无论文证据");
    if (state.locale === "en") {
      return [
        "## Knowledge Architecture",
        `This Wiki architecture is assembled from ${sourceNodes.length} knowledge nodes and ${sourceEdges.length} relations.`,
        "## Current Themes",
        themes,
        "## Evidence Sources",
        `- Reading papers: ${counts.paper}`,
        `- Sections / method snippets: ${counts.section}`,
        `- User direction nodes: ${counts.profile}`,
        "## Representative Papers",
        papers
      ].join("\n");
    }
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
    const label = localizeWikiText(entry.label);
    const papers = relatedPapers.map((paper) => `- ${graphTitle(paper)}`).join("\n") || (state.locale === "en" ? "- No direct paper evidence yet" : "- 暂无直接论文证据");
    if (state.locale === "en") {
      return [
        `## ${label}`,
        `This theme is extracted from ${entry.nodeIds.size} Wiki entries; it is not a fixed template node.`,
        "## Related Evidence",
        papers,
        "## Why It Helps",
        "It helps users quickly understand the current research center of gravity and jump into papers, sections, and reading reports."
      ].join("\n");
    }
    return [
      `## ${label}`,
      `这是从 ${entry.nodeIds.size} 个 Wiki 条目中抽取出的知识库主题，不是固定模板节点。`,
      "## 关联证据",
      papers,
      "## 展示意义",
      "用于帮助用户快速理解当前知识库的研究重心，并继续跳转到论文、章节和精读报告。"
    ].join("\n");
  }

  function userDirectionBody(userNodes, topPapers, entries) {
    const signals = userNodes.flatMap((node) => String(node.keywords || "").split(/[,\s]+/)).filter(Boolean).map(localizeWikiText).slice(0, 8);
    const joiner = state.locale === "en" ? ", " : "、";
    const papers = topPapers.slice(0, 3).map((paper) => `- ${graphTitle(paper)}`).join("\n") || (state.locale === "en" ? "- No deep-reading records yet" : "- 暂无精读记录");
    if (state.locale === "en") {
      return [
        "## User Direction",
        "This summarizes user feedback, deep-reading records, profile nodes, and interest drift to explain why these themes are centered in the graph.",
        "## Current Signals",
        signals.length ? signals.join(joiner) : entries.slice(0, 4).map((entry) => localizeWikiText(entry.label)).join(joiner) || "No stable signals yet",
        "## Recent Evidence",
        papers
      ].join("\n");
    }
    return [
      "## 用户方向",
      "这里汇总用户反馈、精读记录、画像节点和兴趣漂移，用来解释为什么这些主题被放在图谱中心。",
      "## 当前信号",
      signals.length ? signals.join("、") : entries.slice(0, 4).map((entry) => localizeWikiText(entry.label)).join("、") || "暂无稳定信号",
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
      title: ui().wiki.architecture,
      node_type: "topic",
      type: "topic",
      x: 50,
      y: 49,
      size: "core",
      body: architectureBody(ui().wiki.architecture, sourceNodes, sourceEdges, entries, topPapers),
      real_node_id: "",
      source_count: sourceNodes.length,
      related_papers: topPapers
    };

    const userNode = {
      id: "architecture:user-direction",
      node_id: "architecture:user-direction",
      title: state.locale === "en" ? "User Direction" : "用户方向",
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
        body: graphBody(paper) || (state.locale === "en" ? `This paper is core evidence in the current knowledge base: ${graphTitle(paper)}` : `这篇论文是当前知识库中的核心证据：${graphTitle(paper)}`),
        real_node_id: graphId(paper),
        source_count: 1,
        related_papers: [paper]
      };
    });

    const mapNodes = [coreNode, ...topicNodes, ...methodNodes, userNode, ...paperNodes];
    const mapEdges = [
      { src_id: userNode.id, dst_id: coreNode.id, relation: state.locale === "en" ? "User direction" : "用户方向", weight: 1.2 },
      ...topicNodes.map((node) => ({ src_id: coreNode.id, dst_id: node.id, relation: state.locale === "en" ? "Theme" : "主题", weight: 1.1 })),
      ...methodNodes.map((node) => ({ src_id: coreNode.id, dst_id: node.id, relation: state.locale === "en" ? "Method" : "方法", weight: 0.85 })),
      ...paperNodes.map((node, index) => ({
        src_id: topicNodes[index % Math.max(1, topicNodes.length)]?.id || coreNode.id,
        dst_id: node.id,
        relation: state.locale === "en" ? "Paper evidence" : "论文证据",
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
    const sourceNodes = uniqueGraphNodes((nodes || []).filter((node) => graphId(node).trim()));
    const sourceNodeIds = new Set(sourceNodes.map((node) => graphId(node)));
    const sourceEdges = (edges || [])
      .map(normalizeGraphEdge)
      .filter((edge) => sourceNodeIds.has(edge.src_id) && sourceNodeIds.has(edge.dst_id));
    const degree = graphDegreeMap(sourceNodes, sourceEdges);
    const groups = {
      topic: { x: 26, y: 31, nodes: [] },
      paper: { x: 42, y: 64, nodes: [] },
      method: { x: 70, y: 58, nodes: [] },
      frontier: { x: 74, y: 28, nodes: [] }
    };
    sourceNodes
      .slice()
      .sort((a, b) => (degree[graphId(b)] || 0) - (degree[graphId(a)] || 0))
      .forEach((node) => {
        const type = graphType(node);
        (groups[type] || groups.topic).nodes.push(node);
      });

    const mapNodes = [];
    Object.entries(groups).forEach(([type, group]) => {
      const count = Math.max(1, group.nodes.length);
      group.nodes.forEach((node, index) => {
        const ring = Math.floor(index / 18);
        const slot = index % 18;
        const angle = (slot / Math.min(18, count)) * Math.PI * 2 + ring * 0.38;
        const radiusX = 7 + ring * 6 + (type === "paper" ? 3 : 0);
        const radiusY = 6 + ring * 4.5 + (type === "paper" ? 2 : 0);
        const id = graphId(node);
        const score = degree[id] || 0;
        mapNodes.push({
          ...node,
          id,
          node_id: id,
          type,
          x: clamp(group.x + Math.cos(angle) * radiusX, 5, 94),
          y: clamp(group.y + Math.sin(angle) * radiusY, 8, 91),
          size: score >= 2.5 ? "large" : score >= 1.0 ? "medium" : "small",
          real_node_id: id
        });
      });
    });
    const map = {
      nodes: mapNodes,
      edges: sourceEdges,
      sourceNodes,
      sourceEdges,
      byId: Object.fromEntries(mapNodes.map((node) => [node.id, node]))
    };
    state.wikiMap = map;
    const focusId = state.currentWikiNodeId && map.byId[state.currentWikiNodeId]
      ? state.currentWikiNodeId
      : pickWikiFocusNodeId();
    return {
      nodes: map.nodes.map((node) => ({ ...node, x: node.x, y: node.y, type: node.type, size: node.size })),
      edges: map.edges,
      centerId: focusId || graphId(map.nodes[0] || {}),
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
          <strong>${escapeHtml(ui().wiki.emptyGraphTitle)}</strong>
          <p>${escapeHtml(ui().wiki.emptyGraphBody)}</p>
        </div>
      `;
      return;
    }
    const spread = state.wikiGraphTransform.scale;
    const visualNodes = layout.nodes.map((node) => ({
      ...node,
      x: 50 + (Number(node.x) - 50) * spread,
      y: 50 + (Number(node.y) - 50) * spread
    }));
    const byId = Object.fromEntries(visualNodes.map((node) => [node.id, node]));
    const lineHtml = layout.edges.map((edge, index) => {
      const a = byId[String(edge.src_id)];
      const b = byId[String(edge.dst_id)];
      if (!a || !b) return "";
      const weightClass = graphWeight(edge) >= 0.78 || a.id === layout.centerId || b.id === layout.centerId
        ? "strong"
        : graphWeight(edge) >= 0.35 ? "medium" : "light";
      const curve = (index % 2 === 0 ? 4 : -4) * Math.max(0.8, Math.min(spread, 1.8));
      const midX = (a.x + b.x) / 2 + curve;
      const midY = (a.y + b.y) / 2 - curve;
      return `<path class="graph-svg-link ${weightClass}" d="M ${a.x} ${a.y} Q ${midX} ${midY} ${b.x} ${b.y}"></path>`;
    }).join("");
    const activeNodeId = state.currentWikiNodeId || layout.centerId;
    const nodeZoom = Math.max(0.82, Math.min(1.18, 0.9 + spread * 0.1));
    const labelZoom = Math.max(0.9, Math.min(1.22, 0.94 + spread * 0.08));
    const nodeHtml = visualNodes.map((node) => `
      <button
        class="graph-node ${node.type} ${node.size || "medium"} ${node.id === activeNodeId ? "active" : ""}"
        data-node-id="${escapeHtml(graphId(node))}"
        data-real-node-id="${escapeHtml(node.real_node_id || "")}"
        data-node-title="${escapeHtml(rawGraphTitle(node))}"
        data-node-body="${escapeHtml(rawGraphBody(node))}"
        title="${escapeHtml(graphTitle(node))}"
        style="left:${node.x}%;top:${node.y}%;--node-zoom:${nodeZoom};--label-zoom:${labelZoom}"
        type="button"
      >
        <span class="node-dot"></span>
        <span class="node-label">${escapeHtml(graphTitle(node))}</span>
      </button>
    `).join("");
    target.classList.toggle("real", hasBackendGraph);
    const totalNodes = Number(state.wikiStats?.nodes || layout.sourceCount || 0);
    const graphNote = hasBackendGraph
      ? ui().wiki.graphRealNote(layout.nodes.length, totalNodes, layout.sourceEdgeCount)
      : state.wikiNodes.length
        ? ui().wiki.graphSearchNote(layout.sourceCount, layout.nodes.length)
        : ui().wiki.graphDemoNote;
    target.innerHTML = `
      <div class="graph-canvas">
        <div class="graph-viewport">
          <svg class="graph-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${lineHtml}</svg>
          ${nodeHtml}
        </div>
        <div class="graph-legend">
          <span><i class="legend-dot topic"></i>${escapeHtml(ui().wiki.legend.topic)}</span>
          <span><i class="legend-dot method"></i>${escapeHtml(ui().wiki.legend.method)}</span>
          <span><i class="legend-dot paper"></i>${escapeHtml(ui().wiki.legend.paper)}</span>
          <span><i class="legend-dot frontier"></i>${escapeHtml(ui().wiki.legend.frontier)}</span>
        </div>
        <div class="graph-tools" aria-label="${escapeHtml(ui().wiki.toolsLabel)}">
          <button data-graph-action="zoom-in" type="button" title="${escapeHtml(ui().wiki.zoomIn)}">＋</button>
          <button data-graph-action="zoom-out" type="button" title="${escapeHtml(ui().wiki.zoomOut)}">－</button>
          <button data-graph-action="focus" type="button" title="${escapeHtml(ui().wiki.focusCenter)}">⌖</button>
        </div>
      </div>
      <div class="graph-note">${graphNote}</div>
    `;
    applyWikiGraphTransform();
  }

  function clampWikiGraphPan() {
    const graph = $("wikiGraph");
    if (!graph) return;
    const rect = graph.getBoundingClientRect();
    const scale = state.wikiGraphTransform.scale;
    const limitX = Math.max(180, rect.width * scale * 0.7);
    const limitY = Math.max(180, rect.height * scale * 0.7);
    state.wikiGraphTransform.x = clamp(state.wikiGraphTransform.x, -limitX, limitX);
    state.wikiGraphTransform.y = clamp(state.wikiGraphTransform.y, -limitY, limitY);
  }

  function applyWikiGraphTransform() {
    clampWikiGraphPan();
    const viewport = $("wikiGraph")?.querySelector(".graph-viewport");
    if (!viewport) return;
    const { scale, x, y } = state.wikiGraphTransform;
    viewport.style.transform = `translate(${x}px, ${y}px)`;
    viewport.dataset.zoom = scale.toFixed(2);
  }

  function zoomWikiGraph(delta) {
    const previousScale = state.wikiGraphTransform.scale;
    state.wikiGraphTransform.scale = clamp(previousScale * delta, 0.45, 2.4);
    if (state.wikiView === "graph") renderWikiGraph();
  }

  function resetWikiGraphTransform() {
    state.wikiGraphTransform = { scale: 1, x: 0, y: 0 };
    applyWikiGraphTransform();
  }

  function renderWikiList() {
    const nodes = state.wikiNodes.length ? state.wikiNodes : state.wikiGraph?.nodes?.length ? state.wikiGraph.nodes : DEMO_MODE ? demoWikiNodes : [];
    if (!nodes.length) {
      $("wikiGraph").innerHTML = `
        <div class="wiki-empty-state">
          <strong>${escapeHtml(ui().wiki.emptyListTitle)}</strong>
          <p>${escapeHtml(ui().wiki.emptyListBody)}</p>
        </div>
      `;
      return;
    }
    $("wikiGraph").innerHTML = `
      <div class="wiki-list-view">
        ${nodes.map((node) => `
          <button class="result-item" data-node-id="${escapeHtml(graphId(node))}" data-node-title="${escapeHtml(rawGraphTitle(node))}" data-node-body="${escapeHtml(rawGraphBody(node))}" type="button">
            <h3>${escapeHtml(graphTitle(node))} <span class="status-chip">${escapeHtml(graphTypeLabel(node))}</span></h3>
            <p>${escapeHtml(graphBody(node) || ui().wiki.noSummary)}</p>
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
    return localizeWikiText(String(raw || "related").replaceAll("_", " "));
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
      const typeBoost = graphType(node) === "paper" ? 2.0 : graphType(node) === "topic" ? 1.2 : 0.4;
      const score = (degree[id] || 0) + Number(node.score || 0) + typeBoost;
      const bestNode = nodes.find((item) => graphId(item) === best);
      const bestTypeBoost = bestNode && graphType(bestNode) === "paper" ? 2.0 : bestNode && graphType(bestNode) === "topic" ? 1.2 : 0.4;
      const bestScore = (degree[best] || 0) + Number(bestNode?.score || 0) + bestTypeBoost;
      return score > bestScore ? id : best;
    }, graphId(candidates[0] || nodes[0]));
  }

  function wikiStatsText(stats, suffix = "") {
    const byType = stats.nodes_by_type || {};
    const typeParts = [
      byType.paper ? `${ui().wiki.typePart.paper} ${byType.paper}` : "",
      byType.topic ? `${ui().wiki.typePart.topic} ${byType.topic}` : "",
      byType.section ? `${ui().wiki.typePart.section} ${byType.section}` : "",
      byType.trajectory ? `${ui().wiki.typePart.trajectory} ${byType.trajectory}` : ""
    ].filter(Boolean).join(" · ");
    const wikiDirText = stats.wiki_dir ? ` · ${ui().wiki.dirPrefix} ${stats.wiki_dir}` : "";
    const typeText = typeParts ? ` · ${typeParts}` : "";
    return ui().wiki.stats(stats, typeText, wikiDirText, suffix);
  }

  function wikiDailyGraphParams() {
    const scope = $("wikiDailyScope")?.value || "latest";
    const month = $("wikiDailyMonth")?.value || "";
    const params = new URLSearchParams({
      user_id: currentUser(),
      limit: "80",
      daily_scope: scope
    });
    if (scope === "month" && month) params.set("daily_month", month);
    return params.toString();
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
    const tags = Array.from(new Set(items.map((item) => localizeWikiText(item).trim()).filter(Boolean))).slice(0, 8);
    $("wikiTags").innerHTML = tags.length
      ? tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
      : ui().wiki.defaultTags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  }

  function renderWikiResultNodes(nodes, summary = "") {
    const target = $("wikiResults");
    if (!nodes.length) {
      target.className = "result-list empty";
      target.textContent = ui().wiki.noMatch;
      $("wikiEvidenceSummary").textContent = summary || ui().wiki.itemCount(0);
      renderWikiTags([]);
      return;
    }
    target.className = "result-list";
    target.innerHTML = nodes.map((node) => `
      <button class="result-item" data-node-id="${escapeHtml(node.node_id || graphId(node))}" data-node-title="${escapeHtml(rawGraphTitle(node))}" data-node-body="${escapeHtml(rawGraphBody(node))}" type="button">
        <h3>${escapeHtml(graphTitle(node))} <span class="status-chip">${escapeHtml(graphTypeLabel(node))}</span></h3>
        <p>${escapeHtml(graphBody(node) || ui().wiki.noSummary)}</p>
        <div class="evidence-meta">${wikiEvidenceMeta(node).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </button>
    `).join("");
    $("wikiEvidenceSummary").textContent = summary || ui().wiki.itemCount(nodes.length);
    renderWikiTags(nodes.flatMap((node) => [node.node_type, ...(String(node.keywords || "").split(/[,\s]+/))]));
  }

  function renderWikiRelations(nodeId) {
    const current = graphNodesById()[nodeId];
    const semanticPapers = current?.related_papers || [];
    const allRelated = semanticPapers.length
      ? semanticPapers.map((node) => ({ node, edge: { relation: ui().wiki.relatedPapers, weight: Number(node.score || 1) || 1 } }))
      : nodeId ? relatedWikiNodes(nodeId) : [];
    const paperRelated = allRelated.filter(({ node }) => graphType(node) === "paper");
    const related = [
      ...paperRelated,
      ...allRelated.filter(({ node }) => graphType(node) !== "paper")
    ].slice(0, 4);
    if (!related.length) {
      const fallbackNodes = state.wikiGraph?.nodes?.length ? state.wikiGraph.nodes.slice(0, 10) : state.wikiNodes.slice(0, 10);
      renderWikiResultNodes(fallbackNodes.filter((node) => graphId(node) !== nodeId), fallbackNodes.length ? ui().wiki.graphNodes : ui().wiki.itemCount(0));
      return;
    }

    $("wikiResults").className = "result-list";
    $("wikiResults").innerHTML = related.map(({ node, edge }) => `
      <button class="result-item relationship-row" data-node-id="${escapeHtml(graphId(node))}" data-node-title="${escapeHtml(rawGraphTitle(node))}" data-node-body="${escapeHtml(rawGraphBody(node))}" type="button">
        <h3>${escapeHtml(graphTitle(node))} <span class="status-chip">${escapeHtml(graphTypeLabel(node))}</span></h3>
        <p>${escapeHtml(graphBody(node) || ui().wiki.noSummary)}</p>
        <div class="evidence-meta">
          <span>${escapeHtml(relationLabel(edge.relation))}</span>
          <span>${Math.round(graphWeight(edge) * 100)}%</span>
          ${node.file_path ? `<span>${escapeHtml(node.file_path)}</span>` : ""}
        </div>
      </button>
    `).join("");
    $("wikiEvidenceSummary").textContent = ui().wiki.relationCount(related.length);
    renderWikiTags([
      current ? graphTypeLabel(current) : "",
      ...(String(current?.keywords || "").split(/[,\s]+/)),
      ...related.map(({ edge }) => relationLabel(edge.relation)),
      ...related.map(({ node }) => graphTypeLabel(node))
    ]);
  }

  function renderWikiEntryHtml(body) {
    const content = String(body || "").trim();
    if (!content) return `<p>${escapeHtml(ui().wiki.noSummary)}</p>`;
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
    const rawTitle = String(options.rawTitle ?? title ?? ui().wiki.architecture);
    const rawBody = String(options.rawBody ?? body ?? "");
    const displayTitle = options.displayTitle ?? localizeWikiText(rawTitle || ui().wiki.architecture);
    const displayBody = options.displayBody ?? localizeWikiText(rawBody);
    const editNodeId = options.editNodeId || (String(nodeId || "").startsWith("architecture:") ? "" : nodeId || "");
    state.currentWikiNodeId = nodeId || "";
    state.currentWikiEditNodeId = editNodeId;
    state.currentWikiEntry = {
      title: rawTitle,
      body: rawBody,
      nodeId: nodeId || "",
      editNodeId
    };
    $("wikiEntryTitle").dataset.rawTitle = rawTitle;
    $("wikiEntryTitle").textContent = displayTitle || ui().wiki.architecture;
    display.dataset.rawBody = rawBody;
    display.innerHTML = renderWikiEntryHtml(displayBody);
    display.hidden = false;
    editor.hidden = true;
    editButton.disabled = !state.currentWikiEditNodeId;
    editButton.textContent = state.currentWikiEditNodeId ? ui().wiki.edit : ui().wiki.architectureNode;
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
    const type = node.node_type || node.type ? graphTypeLabel(node) : "node";
    const score = node.score !== undefined ? `${normalizeScore(node.score)}%` : "";
    const source = localizeWikiText(node.source || node.paper_title || node.file_path || "");
    return [type, score, source].filter(Boolean).slice(0, 3);
  }

  function setWikiMapFocus(nodeId = "architecture:core") {
    const focus = state.wikiMap?.byId?.[nodeId] || state.wikiMap?.nodes?.[0];
    if (!focus) {
      setWikiEntry(ui().wiki.architecture, ui().wiki.architectureFallbackBody, "", { renderRelations: false });
      renderWikiResultNodes([], ui().wiki.itemCount(0));
      return;
    }
    setWikiEntry(rawGraphTitle(focus), rawGraphBody(focus), graphId(focus), { editNodeId: focus.real_node_id || "" });
  }

  async function loadWiki() {
    const stats = await api(`/api/wiki/stats?user_id=${encodeURIComponent(currentUser())}`);
    state.wikiStats = stats;
    $("wikiNodeStat").textContent = stats.nodes || 0;
    $("wikiSettingStat").textContent = stats.nodes || "-";
    $("wikiStats").textContent = wikiStatsText(stats);
    try {
      state.wikiGraph = await api(`/api/wiki/graph?${wikiDailyGraphParams()}`);
    } catch (error) {
      console.warn("Wiki graph unavailable, falling back to search nodes.", error);
      state.wikiGraph = null;
    }
    state.wikiNodes = state.wikiGraph?.nodes || [];
    if (!state.wikiNodes.length && Number(stats.nodes || 0) > 0) {
      const fallback = await api(`/api/wiki/search?user_id=${encodeURIComponent(currentUser())}&limit=120`);
      state.wikiNodes = fallback.nodes || [];
      if (state.wikiNodes.length) {
        state.wikiGraph = {
          ok: true,
          nodes: state.wikiNodes,
          edges: state.wikiGraph?.edges || [],
          source: "wiki_search_fallback",
          query: ""
        };
        $("wikiStats").textContent = wikiStatsText(stats, ui().wiki.restoredSuffix);
      }
    }
    if (state.wikiView === "graph") {
      renderWikiGraph();
      setWikiMapFocus(pickWikiFocusNodeId() || "architecture:core");
    } else {
      const focusId = pickWikiFocusNodeId();
      const focusNode = graphNodesById()[focusId];
      if (focusNode) {
        setWikiEntry(rawGraphTitle(focusNode), rawGraphBody(focusNode), graphId(focusNode));
      } else {
        setWikiEntry(ui().wiki.architecture, ui().wiki.architectureFallbackBody, "", { renderRelations: false });
        renderWikiResultNodes([], ui().wiki.itemCount(0));
      }
      renderWikiList();
    }
  }

  async function refreshWiki() {
    const data = await api("/api/wiki/refresh", {
      method: "POST",
      body: JSON.stringify({ user_id: currentUser() })
    });
    await loadWiki();
    const daily = data.daily_notes || {};
    const noteCount = Array.isArray(daily.daily_notes) ? daily.daily_notes.length : 0;
    const errorCount = Array.isArray(daily.errors) ? daily.errors.length : 0;
    const detail = [
      ui().wiki.refreshDetail(daily, noteCount)
    ].join(" · ");
    showFeedbackToast(
      errorCount ? "warning" : "success",
      errorCount ? ui().wiki.refreshPartial : ui().wiki.refreshDone,
      errorCount ? `${detail} · ${daily.errors[0]}` : detail
    );
  }

  function githubSyncSummary(data) {
    const labels = ui().wiki.githubSync;
    const parts = [];
    if (data.pulled) parts.push(labels.pulled);
    if (data.committed) parts.push(labels.committed(data.commit || ""));
    if (data.pushed) parts.push(labels.pushed);
    if (!parts.length) parts.push(labels.unchanged);
    return parts.join(" · ");
  }

  async function syncGithubNotes() {
    try {
      const data = await api("/api/github/sync", {
        method: "POST",
        body: JSON.stringify({ user_id: currentUser(), response_language: responseLanguage() })
      });
      await loadSettings();
      await loadWiki();
      const llm = data.llm_review || {};
      const summary = githubSyncSummary(data);
      const labels = ui().wiki.githubSync;
      const detail = [
        `${labels.repoDir}: ${data.repo_dir || "-"}`,
        `${labels.remote}: ${data.remote || "-"}`,
        `${labels.branch}: ${data.branch || "main"}`,
        data.pull_warning ? `${labels.warning}: ${data.pull_warning}` : "",
        llm.summary ? `${labels.llmReview}: ${llm.summary}` : ""
      ].filter(Boolean).join("\n");
      $("wikiStats").textContent = `${summary} · GitHub`;
      setWikiEntry(labels.resultTitle, detail, "", { renderRelations: false });
      showFeedbackToast("success", labels.successTitle, summary);
    } catch (error) {
      const message = error.message || String(error);
      $("wikiStats").textContent = ui().wiki.githubSync.failureTitle;
      showFeedbackToast("error", ui().wiki.githubSync.failureTitle, message);
      error.paperflowToastShown = true;
      throw error;
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
      const graph = await api(`/api/wiki/graph?user_id=${encodeURIComponent(currentUser())}&q=${encodeURIComponent(rawQuery)}&limit=120`);
      if (graph.nodes?.length) state.wikiGraph = graph;
    } catch (error) {
      console.warn("Wiki search graph unavailable.", error);
    }
    renderWikiResultNodes(nodes, ui().wiki.resultsCount(nodes.length));
    if (nodes[0]) setWikiEntry(rawGraphTitle(nodes[0]), rawGraphBody(nodes[0]), nodes[0].node_id || graphId(nodes[0]), { renderRelations: false });
    if (state.wikiView === "graph") renderWikiGraph();
    if (state.wikiView === "list") renderWikiList();
  }

  function normalizeCitationSource(source, index = 0) {
    const metadata = source?.metadata || {};
    const citationIndex = Number(source?.index || index + 1);
    const nodeType = source?.node_type || source?.type || "";
    const sourceType = source?.source_type || "";
    const sourceId = source?.source_id || "";
    const rawMeta = source?.meta || [sourceType, sourceId].filter(Boolean).join(" · ") || ui().chat.sourceDefault;
    const meta = state.locale === "en"
      ? String(rawMeta).replaceAll("精读报告", "Reading report").replaceAll("论文推荐", "Paper recommendation").replaceAll("手动导入", "Manual import").replaceAll("参考文献", "Reference")
      : rawMeta;
    const title = String(source?.title || source?.node_id || ui().chat.sourceTitle(citationIndex)).replace(/^Wiki:\s*/i, "").replace(/^Q\d+[\s:-]*/i, "");
    return {
      index: citationIndex,
      node_id: source?.node_id || source?.id || "",
      node_type: nodeType,
      title: localizeWikiText(title),
      meta: localizeWikiText(meta),
      snippet: localizeWikiText(source?.snippet || source?.excerpt || source?.body || ""),
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
    if (!escaped) return `<p>${escapeHtml(ui().chat.generating)}</p>`;
    const linked = escaped.replace(/\[(\d{1,3})\]/g, (match, index) => {
      if (!refs.has(String(index))) return match;
      const citation = refs.get(String(index));
      return `<button type="button" class="citation-ref" data-citation-index="${index}" title="${escapeHtml(citation.title)}">[${index}]</button>`;
    }).replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");
    return linked
      .split(/\n{2,}/)
      .map((block) => `<p>${block.replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  function routingLabel(reason) {
    return ui().chat.routing[reason] || reason || "";
  }

  function renderAnswerMeta(data = {}, citations = []) {
    const wikiMode = data.retrieval_required !== false && data.mode !== "direct";
    const modeText = wikiMode ? ui().chat.referencesCount(citations.length) : ui().chat.directAnswer;
    const route = wikiMode && data.routing_reason !== "mention_required" ? "" : routingLabel(data.routing_reason);
    return `
      <div class="answer-meta">
        <span class="${wikiMode ? "wiki" : "direct"}">${escapeHtml(modeText)}</span>
        ${route ? `<span>${escapeHtml(route)}</span>` : ""}
        <span>${escapeHtml(ui().chat.streamOutput)}</span>
      </div>
    `;
  }

  function renderChatSources(sources = DEMO_MODE ? demoSources : []) {
    const items = Array.isArray(sources) ? sources.map((source, index) => normalizeCitationSource(source, index)) : [];
    state.chatSources = items;
    $("chatSources").className = items.length ? "source-list" : "source-list empty";
    $("chatSources").innerHTML = items.length ? items.map((source) => {
      const openControl = source.url
        ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(ui().chat.openSource)}</a>`
        : `<button type="button" data-open-citation-source data-node-id="${escapeHtml(source.node_id)}" data-title="${escapeHtml(source.title)}">${escapeHtml(ui().chat.viewSource)}</button>`;
      return `
        <div class="source-card citation-card" tabindex="0" data-citation-index="${escapeHtml(source.index)}" data-node-id="${escapeHtml(source.node_id)}" data-title="${escapeHtml(source.title)}">
          <h3>[${escapeHtml(source.index)}] ${escapeHtml(source.title)}</h3>
          <p>${escapeHtml(source.meta)}</p>
          ${source.snippet ? `<p>${escapeHtml(source.snippet)}</p>` : ""}
          ${openControl}
        </div>
      `;
    }).join("") : ui().chat.sourcesEmpty;
  }

  function chatIntroHtml() {
    return `
      <div class="message assistant">
        <div class="avatar">AI</div>
        <div class="bubble">
          <p>${escapeHtml(ui().chat.intro)}</p>
        </div>
      </div>
    `;
  }

  function resetChatThread() {
    state.chatMessages = [];
    $("chatThread").innerHTML = chatIntroHtml();
    renderChatSources();
    window.setTimeout(() => {
      $("chatThread").scrollTop = $("chatThread").scrollHeight;
    }, 0);
  }

  function formatChatDateLabel(dateValue) {
    const date = String(dateValue || "").slice(0, 10);
    if (!date) return ui().chat.ungrouped;
    if (date === todayDateValue()) return ui().chat.today;
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayValue = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`;
    if (date === yesterdayValue) return ui().chat.yesterday;
    return date;
  }

  function formatChatTime(value) {
    const text = String(value || "");
    const match = text.match(/(\d{2}):(\d{2})/);
    return match ? `${match[1]}:${match[2]}` : "";
  }

  function renderChatHistory(data = {}) {
    const sessions = Array.isArray(data.sessions) ? data.sessions : state.chatHistory;
    let groups = Array.isArray(data.groups) ? data.groups : state.chatHistoryGroups;
    if ((!groups || !groups.length) && sessions.length) {
      const grouped = {};
      sessions.forEach((session) => {
        const date = String(session.updated_at || session.created_at || todayDateValue()).slice(0, 10);
        if (!grouped[date]) grouped[date] = [];
        grouped[date].push(session);
      });
      groups = Object.keys(grouped).map((date) => ({ date, sessions: grouped[date] }));
    }
    state.chatHistory = sessions;
    state.chatHistoryGroups = groups || [];

    const hint = $("chatHistoryHint");
    if (hint) hint.textContent = sessions.length ? ui().chat.conversations(sessions.length) : ui().chat.historyHint;

    const target = $("chatHistoryList");
    target.className = sessions.length ? "chat-history-list" : "chat-history-list empty";
    if (!sessions.length) {
      target.innerHTML = ui().chat.historyEmptyDetail;
      return;
    }
    target.innerHTML = state.chatHistoryGroups.map((group) => `
      <div class="chat-history-date">
        <div class="chat-history-date-title">${escapeHtml(formatChatDateLabel(group.date))}</div>
        ${(group.sessions || []).map((session) => `
          <button
            class="chat-session-button${session.session_id === state.chatSessionId ? " active" : ""}"
            type="button"
            data-chat-session-id="${escapeHtml(session.session_id)}"
            title="${escapeHtml(session.title || ui().chat.newChatTitle)}"
          >
            <strong>${escapeHtml(session.title || ui().chat.newChatTitle)}</strong>
            <span>${escapeHtml(formatChatTime(session.updated_at))}${session.message_count ? ` · ${escapeHtml(ui().chat.messageCount(session.message_count))}` : ""}</span>
          </button>
        `).join("")}
      </div>
    `).join("");
  }

  function renderChatMessages(messages = []) {
    state.chatMessages = messages;
    if (!messages.length) {
      resetChatThread();
      return;
    }
    let latestCitations = [];
    $("chatThread").innerHTML = messages.map((message) => {
      const role = message.role === "user" ? "user" : "assistant";
      const content = String(message.content || "");
      if (role === "user") {
        return `
          <div class="message user" data-chat-message-id="${escapeHtml(message.id || "")}">
            <div class="avatar">${escapeHtml(ui().chat.me)}</div>
            <div class="bubble"><p>${escapeHtml(content).replace(/\n/g, "<br>")}</p></div>
          </div>
        `;
      }
      const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : {};
      const answerData = {
        mode: "direct",
        retrieval_required: false,
        ...metadata,
        text: content
      };
      const citations = normalizeCitations(answerData);
      latestCitations = citations;
      return `
        <div class="message assistant" data-chat-message-id="${escapeHtml(message.id || "")}">
          <div class="avatar">AI</div>
          <div class="bubble">
            ${renderAnswerMeta(answerData, citations)}
            <div class="answer-text">${renderAnswerWithCitations(content, citations)}</div>
          </div>
        </div>
      `;
    }).join("");
    renderChatSources(latestCitations);
    window.setTimeout(() => {
      $("chatThread").scrollTop = $("chatThread").scrollHeight;
    }, 0);
  }

  function renderChatHistoryUnavailable() {
    state.chatHistoryLoaded = false;
    state.chatHistory = [];
    state.chatHistoryGroups = [];
    state.chatMessages = [];
    const hint = $("chatHistoryHint");
    if (hint) hint.textContent = ui().chat.backendRestart;
    const target = $("chatHistoryList");
    target.className = "chat-history-list empty";
    target.innerHTML = ui().chat.historyUnavailable;
  }

  async function loadChatSessions(options = {}) {
    let data;
    try {
      data = await api(`/api/chat/sessions?user_id=${encodeURIComponent(currentUser())}&days=90&limit=120`);
    } catch (error) {
      if (isUnknownApiRoute(error, "/api/chat/sessions")) {
        renderChatHistoryUnavailable();
        return;
      }
      throw error;
    }
    state.chatHistoryLoaded = true;
    renderChatHistory(data);
    if (options.openLatest && !state.chatSessionId) {
      const latest = state.chatHistory[0];
      if (latest?.session_id) {
        await loadChatSession(latest.session_id);
      } else {
        resetChatThread();
      }
    }
  }

  async function loadChatSession(sessionId) {
    const normalizedSessionId = String(sessionId || "").trim();
    if (!normalizedSessionId) {
      startNewChat({ silent: true });
      return;
    }
    const token = ++state.chatLoadToken;
    let data;
    try {
      data = await api(`/api/chat/session?user_id=${encodeURIComponent(currentUser())}&session_id=${encodeURIComponent(normalizedSessionId)}`);
    } catch (error) {
      if (isUnknownApiRoute(error, "/api/chat/session")) {
        renderChatHistoryUnavailable();
        return;
      }
      throw error;
    }
    if (token !== state.chatLoadToken) return;
    if (!data.session) throw new Error(ui().chat.missingSession);
    state.chatSessionId = data.session.session_id || normalizedSessionId;
    renderChatMessages(data.messages || []);
    renderChatHistory({ sessions: state.chatHistory, groups: state.chatHistoryGroups });
  }

  async function clearChatHistory() {
    const count = state.chatHistory.length;
    if (!count) {
      showFeedbackToast("warning", ui().chat.noHistoryTitle, ui().chat.noHistoryDetail);
      return;
    }
    const confirmed = window.confirm(ui().chat.clearConfirm(count));
    if (!confirmed) return;
    const data = await api("/api/chat/sessions/clear", {
      method: "POST",
      body: JSON.stringify({ user_id: currentUser() })
    });
    state.chatSessionId = "";
    state.chatHistory = [];
    state.chatHistoryGroups = [];
    resetChatThread();
    renderChatSources([]);
    renderChatHistory({ sessions: [], groups: [] });
    showFeedbackToast("success", ui().chat.clearedTitle, ui().chat.clearedDetail(data.deleted || count));
  }

  function startNewChat(options = {}) {
    state.chatSessionId = "";
    state.chatLoadToken += 1;
    if ($("chatInput")) $("chatInput").value = "";
    clearChatMentions();
    window.clearTimeout(state.mentionSearchTimer);
    state.mentionSearchToken += 1;
    if ($("mentionSuggestions")) $("mentionSuggestions").hidden = true;
    resetChatThread();
    renderChatHistory({ sessions: state.chatHistory, groups: state.chatHistoryGroups });
    if (!options.silent) {
      showFeedbackToast("success", ui().chat.newChatToastTitle, ui().chat.newChatToastDetail);
    }
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
    if (!response.ok || !response.body) throw new Error(ui().chat.streamUnavailable);

    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = "";
    let text = "";
    let result = {};
    let citations = [];
    let doneReceived = false;

    const processFrame = (frame) => {
      if (!frame.trim()) return;
      const parsed = parseSseFrame(frame);
      if (!parsed) return;
      if (parsed.event === "error") throw new Error(parsed.data.error || ui().chat.streamFailed);
      if (parsed.event === "status" && !text) {
        answerTarget.innerHTML = `<p>${escapeHtml(parsed.data.text || ui().chat.generating)}</p>`;
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
        doneReceived = true;
        result = { ...result, ...parsed.data };
        text = parsed.data.text || text;
        citations = normalizeCitations(parsed.data);
        const metaTarget = message.querySelector(".answer-meta");
        if (metaTarget) metaTarget.outerHTML = renderAnswerMeta(parsed.data, citations);
        answerTarget.classList.remove("loading");
        answerTarget.innerHTML = renderAnswerWithCitations(text, citations);
        renderChatSources(citations);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\n\n/);
      buffer = frames.pop() || "";
      frames.forEach(processFrame);
    }
    if (buffer.trim()) {
      processFrame(buffer);
    }
    if (!doneReceived) {
      answerTarget.classList.add("loading");
      answerTarget.innerHTML = `${text ? renderAnswerWithCitations(text, citations) : ""}<p>${escapeHtml(ui().chat.streamInterruptedText)}</p>`;
      throw new Error(ui().chat.streamInterruptedError);
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
        <button type="button" data-remove-mention="${escapeHtml(mention.node_id)}" aria-label="${escapeHtml(ui().chat.removeMention(mention.title))}">×</button>
      </span>
    `).join("");
  }

  function renderMentionSuggestions(nodes = []) {
    const panel = $("mentionSuggestions");
    const items = Array.isArray(nodes) ? nodes.slice(0, 6) : [];
    panel.hidden = !items.length;
    panel.innerHTML = items.map((node) => {
      const nodeId = node.node_id || node.id || node.title || "";
      const title = graphTitle({ ...node, title: node.title || nodeId || ui().chat.unnamedNode });
      const meta = [graphTypeLabel(node), node.score ? ui().chat.match(Math.round(Number(node.score) * 100)) : ""].filter(Boolean).join(" · ");
      const body = graphBody(node);
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
    const data = await api(`/api/wiki/mentions?user_id=${encodeURIComponent(currentUser())}&q=${encodeURIComponent(context.query)}&limit=6`);
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
      mentions: activeMentionsForQuestion(question),
      session_id: state.chatSessionId || "",
      response_language: responseLanguage()
    };
    $("chatThread").insertAdjacentHTML("beforeend", `
      <div class="message user">
        <div class="avatar">${escapeHtml(ui().chat.me)}</div>
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
          <div class="answer-meta"><span>${escapeHtml(ui().chat.preparing)}</span></div>
          <div class="answer-text loading"><p>${escapeHtml(ui().chat.generating)}</p></div>
        </div>
      </div>
    `);
    const message = $(messageId);
    const metaTarget = message.querySelector(".answer-meta");
    const answerTarget = message.querySelector(".answer-text");
    const previousText = button.textContent;
    button.disabled = true;
    button.textContent = ui().papers.generating;

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
          showFeedbackToast("warning", ui().chat.streamInterruptedTitle, ui().chat.streamInterruptedDetail);
          data = await api("/api/wiki/ask", { method: "POST", body: JSON.stringify(payload) });
          const citations = normalizeCitations(data);
          const currentMeta = message.querySelector(".answer-meta");
          if (currentMeta) currentMeta.outerHTML = renderAnswerMeta(data, citations);
          await streamAnswerText(answerTarget, data.text || "", citations);
          renderChatSources(citations);
        }
        const citations = normalizeCitations(data);
      }
      if (data?.session_id) {
        state.chatSessionId = data.session_id;
      }
      try {
        await loadChatSessions();
      } catch (historyError) {
        console.warn("Chat history refresh failed.", historyError);
        const detail = isUnknownApiRoute(historyError, "/api/chat/sessions")
          ? ui().chat.historyRestartDetail
          : ui().chat.historyReloadDetail;
        showFeedbackToast("warning", ui().chat.historyRefreshFailedTitle, detail);
      }
      $("chatThread").scrollTop = $("chatThread").scrollHeight;
    } catch (error) {
      answerTarget.classList.remove("loading");
      answerTarget.innerHTML = `<p>${escapeHtml(ui().chat.generationFailed(error.message || String(error)))}</p>`;
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
    ["settingEnableArxiv", "settingEnableOpenReview"].forEach((id) => {
      $(id).addEventListener("change", () => syncDailySourceControls({
        ...(state.settings?.source_preferences || {}),
        enable_arxiv: $("settingEnableArxiv").checked,
        enable_openreview: $("settingEnableOpenReview").checked,
        arxiv_categories: selectedSettingTagValues("settingArxivCategories"),
        conferences: selectedSettingConferences()
      }));
    });
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
        ? hasConferenceAuth ? ui().settings.authConfigured : ui().settings.authWaiting
        : normalized === "manual" ? ui().settings.manualFirst : ui().settings.publicFirstStatus;
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

    setSourceStatus("semanticScholarAuthStatus", ui().settings.apiKeyConfigured, ui().settings.semanticOptional, semanticKey.present);
    setSourceStatus("openReviewAuthStatus", ui().settings.authConfigured, ui().settings.openReviewPublic, hasOpenReviewAuth);
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
        <input id="env_${escapeHtml(info.key)}" data-env-key="${escapeHtml(info.key)}" value="${escapeHtml(value)}" type="${type}" placeholder="${info.present ? "" : ui().settings.placeholderMissing}">
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
      : `<span>${escapeHtml(ui().settings.placeholderMissing)}</span>`;
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
    return values.length ? values.join(state.locale === "en" ? ", " : "、") : ui().settings.profileFields.notRecorded;
  }

  function editableListValue(items) {
    return splitListValue(items).join("; ");
  }

  function editableWeightedValue(rawMap, items) {
    const entries = Object.entries(rawMap || {});
    if (entries.length) {
      return entries
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .map(([key, value]) => `${key}:${Number(value || 1)}`)
        .join("; ");
    }
    return splitListValue(items).join("; ");
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
    const normalized = firstText(value) || ui().settings.profileFields.notRecorded;
    const emptyClass = normalized === ui().settings.profileFields.notRecorded ? " empty" : "";
    const variantClass = variant ? ` ${variant}` : "";
    return `<div class="profile-info-item${variantClass}${emptyClass}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(normalized)}</strong></div>`;
  }

  function profileEditItem(label, id, value, variant = "wide", multiline = false, hint = "") {
    const variantClass = variant ? ` ${variant}` : "";
    const escapedValue = escapeHtml(value || "");
    const placeholder = hint ? ` placeholder="${escapeHtml(hint)}"` : "";
    const control = multiline
      ? `<textarea id="${escapeHtml(id)}" rows="2"${placeholder}>${escapedValue}</textarea>`
      : `<input id="${escapeHtml(id)}" value="${escapedValue}"${placeholder}>`;
    const hintText = hint ? `<small>${escapeHtml(hint)}</small>` : "";
    return `<label class="profile-info-item editable${variantClass}"><span>${escapeHtml(label)}</span>${control}${hintText}</label>`;
  }

  function renderProfileInfoGrid(profile, raw, userInfo, details) {
    const target = $("profileInfoGrid");
    if (!target) return;
    const mustRead = profileMustReadValues(profile, raw);
    const drift = profile?.drift_state || raw?.drift_state || {};
    const updatedAt = firstText(profile?.updated_at, raw?.updated_at, userInfo?.updated_at);
    const labels = ui().settings.profileFields;
    target.innerHTML = [
      profileInfoItem(labels.user, details.userId),
      profileInfoItem(labels.role, userInfo?.role_name || userInfo?.label || ""),
      profileInfoItem(labels.version, firstText(profile?.version, raw?.version)),
      profileInfoItem(labels.updatedAt, updatedAt),
      profileInfoItem(labels.affiliation, profileAffiliation(raw, userInfo), "wide"),
      profileEditItem(labels.directions, "profileDirectionsInput", editableWeightedValue(raw?.core_directions || profile?.core_directions, details.directions), "wide", true, labels.weightedHint),
      profileEditItem(labels.keywords, "profileKeywordsInput", editableListValue(mustRead.keywords), "wide", true, labels.listHint),
      profileEditItem(labels.authors, "profileAuthorsInput", editableListValue(mustRead.authors), "wide", true, labels.listHint),
      profileEditItem(labels.institutions, "profileInstitutionsInput", editableListValue(mustRead.institutions), "wide", true, labels.listHint),
      profileEditItem(labels.topics, "profileTopicsInput", editableWeightedValue(raw?.topic_weights || profile?.topic_weights, details.topics), "wide", true, labels.topicHint),
      profileInfoItem(labels.drift, firstText(drift.status, raw?.drift_status), "wide")
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
    $("resetProfile").checked = false;

    const updatedAt = firstText(profile.updated_at, raw.updated_at, userInfo.updated_at);
    const labels = ui().settings.profileFields;
    setProfileSyncStatus(updatedAt ? `${labels.loaded} · ${updatedAt}` : (userInfo.has_profile ? labels.loaded : labels.missing));
  }

  async function loadCurrentProfile() {
    const userId = currentUser();
    if (!userId) return;
    const token = ++state.profileLoadToken;
    setProfileSyncStatus(ui().settings.profileFields.loading);
    const data = await api(`/api/profile?user_id=${encodeURIComponent(userId)}`);
    if (token !== state.profileLoadToken) return;
    renderProfileForm(data);
  }

  function conferenceAccessInfo(item) {
    const source = String(item.source || item.label || item.id || "").toLowerCase();
    if (source.includes("openreview")) {
      return {
        method: "OpenReview",
        auth: ui().settings.publicOptionalLogin,
        detail: ui().settings.openReviewDetail,
        priority: ui().settings.priorityHigh
      };
    }
    if (source.includes("aclanthology") || source.includes("anthology")) {
      return {
        method: "ACL Anthology",
        auth: ui().settings.public,
        detail: ui().settings.aclDetail,
        priority: ui().settings.priorityHigh
      };
    }
    if (source.includes("cvf") || source.includes("ecva")) {
      return {
        method: source.includes("ecva") ? "ECVA" : "CVF Open Access",
        auth: ui().settings.public,
        detail: ui().settings.cvfDetail,
        priority: ui().settings.priorityMedium
      };
    }
    if (source.includes("dblp") || source.includes("acm")) {
      return {
        method: source.includes("acm") ? "ACM / DBLP" : "DBLP",
        auth: ui().settings.publicMetadata,
        detail: ui().settings.dblpDetail,
        priority: ui().settings.priorityMedium
      };
    }
    return {
      method: item.source || ui().common.customSource,
      auth: ui().settings.sourceDependent,
      detail: ui().settings.customSourceDetail,
      priority: ui().settings.priorityLow
    };
  }

  function conferenceOptionLabel(item) {
    return item.name || item.label || item.id || item;
  }

  const englishMonthNames = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
  ];

  function formatConferenceTimeline(value) {
    let text = String(value || "").trim();
    if (state.locale !== "en" || !text) return text;
    const phase = { "初": "early", "中": "mid", "底": "late" };
    text = text.replace(/(\d{1,2})\s*-\s*(\d{1,2})\s*月/g, (_match, start, end) => {
      const startMonth = englishMonthNames[Number(start)] || start;
      const endMonth = englishMonthNames[Number(end)] || end;
      return `${startMonth}-${endMonth}`;
    });
    text = text.replace(/(\d{1,2})\s*月\s*(初|中|底)?/g, (_match, month, suffix) => {
      const monthName = englishMonthNames[Number(month)] || month;
      return suffix ? `${phase[suffix] || ""} ${monthName}`.trim() : monthName;
    });
    return text;
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
      target.textContent = ui().settings.noConferenceSources;
      return;
    }

    target.className = "conference-source-list";
    target.innerHTML = conferences.map((item) => {
      const id = item.id || item.name || item.label;
      const label = conferenceOptionLabel(item);
      const info = conferenceAccessInfo(item);
      const checked = configured.size ? configured.has(id) || configured.has(label) : Boolean(item.enabled !== false);
      const disabled = item.enabled === false ? "disabled" : "";
      const timeline = [
        item.acceptance_timeline && ui().settings.announced(formatConferenceTimeline(item.acceptance_timeline)),
        item.conference_date && ui().settings.conferenceDate(formatConferenceTimeline(item.conference_date)),
        item.venue_id
      ].filter(Boolean).join(" · ");
      return `
        <label class="conference-source-item ${checked ? "active" : ""}">
          <input type="checkbox" value="${escapeHtml(id)}" ${checked ? "checked" : ""} ${disabled}>
          <span class="conference-main">
            <strong>${escapeHtml(label)} <em>${escapeHtml(item.group || ui().settings.conferenceGroup)}</em></strong>
            <small>${escapeHtml(info.detail)}</small>
            <small>${escapeHtml(timeline)}</small>
          </span>
          <span class="conference-meta">
            <em>${escapeHtml(info.method)}</em>
            <em>${escapeHtml(info.auth)}</em>
            <em>${escapeHtml(ui().settings.priorityLabel(info.priority))}</em>
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
    `).join("") || `<div><span>rss</span><strong>${escapeHtml(ui().settings.customRssMissing)}</strong><button data-remove-source type="button">×</button></div>`;
  }

  function renderSettings(data) {
    state.settings = data || {};
    const paths = data.paths || {};
    const storageStats = data.storage_stats || {};
    const rowLabels = ui().settings.storageRows;
    const rows = [
      { label: rowLabels.notesRoot, value: paths.notes_root_dir, envKey: "PAPERFLOW_NOTES_ROOT_DIR" },
      { label: rowLabels.pdf, value: paths.pdf_dir, derivedRole: "pdf" },
      { label: rowLabels.reports, value: paths.reading_reports_dir, derivedRole: "reports" },
      { label: rowLabels.wiki, value: paths.wiki_dir, derivedRole: "wiki" },
      { label: rowLabels.notesGit, value: paths.reading_notes_git_dir, derivedRole: "git" },
      { label: rowLabels.notesGitRemote, value: paths.reading_notes_git_remote, envKey: "PAPERFLOW_READING_NOTES_GIT_REMOTE" },
      { label: rowLabels.notesGitBranch, value: paths.reading_notes_git_branch || "main", envKey: "PAPERFLOW_READING_NOTES_GIT_BRANCH" },
      { label: rowLabels.feishu, value: paths.write_feishu ? ui().common.yes : ui().common.no },
      { label: rowLabels.ingest, value: paths.wiki_ingest ? ui().common.yes : ui().common.no }
    ];
    $("settingsList").className = "settings-list";
    $("settingsList").innerHTML = rows.map((row) => `
      <div class="setting-row ${row.envKey ? "editable-path-row" : ""}">
        <strong>${escapeHtml(row.label)}</strong>
        ${row.envKey
          ? `<input data-env-key="${escapeHtml(row.envKey)}" value="${escapeHtml(row.value || "")}" autocomplete="off">`
          : row.derivedRole
            ? `<input data-derived-path="${escapeHtml(row.derivedRole)}" value="${escapeHtml(row.value || "")}" readonly autocomplete="off">`
            : `<span>${escapeHtml(row.value || "-")}</span>`}
      </div>
    `).join("");
    const notesRootInput = document.querySelector('[data-env-key="PAPERFLOW_NOTES_ROOT_DIR"]');
    notesRootInput?.addEventListener("input", updateDerivedNotesPathsPreview);
    updateDerivedNotesPathsPreview();
    if ($("cacheSizeStat")) $("cacheSizeStat").textContent = storageStats.cache_display || "-";

    const env = envMap(data);
    const concurrency = envInfo(env, "PAPERFLOW_MAX_CONCURRENCY", "5");
    const fallbackModel = envInfo(env, "PAPERFLOW_FALLBACK_LLM_MODEL", "GPT-4o");
    if ($("maxConcurrencyInput")) $("maxConcurrencyInput").value = concurrency.value || "5";
    if ($("fallbackModelInput")) $("fallbackModelInput").value = fallbackModel.value || "GPT-4o";
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
    syncDailySourceControls(sourcePrefs);
    document.querySelectorAll("[data-pref-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.prefMode === (reportPrefs.style || "standard"));
    });
    $("directWriteFeishu").checked = Boolean(reportPrefs.write_feishu);
    $("writeFeishuReports").checked = Boolean(reportPrefs.write_feishu);
    $("directPdfWriteFeishu").checked = Boolean(reportPrefs.write_feishu);
    $("wikiIngestSetting").checked = reportPrefs.wiki_ingest !== false;
    if ($("notesGitLlmReviewSetting")) $("notesGitLlmReviewSetting").checked = paths.reading_notes_git_llm_review !== false;
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
    if ($("fallbackModelInput")) {
      values.PAPERFLOW_FALLBACK_LLM_MODEL = $("fallbackModelInput").value;
    }
    values.PAPERFLOW_DEFAULT_ARXIV_CATEGORIES = Array.from($("settingArxivCategories").querySelectorAll("span")).map((item) => item.textContent.trim()).filter(Boolean).join(",");
    values.PAPERFLOW_DEFAULT_CONFERENCES = selectedSettingConferences().join(",");
    values.PAPERFLOW_CUSTOM_RSS_URLS = rssUrls().filter((url) => url !== ui().settings.customRssMissing).join(",");
    values.PAPERFLOW_ENABLE_ARXIV = String($("settingEnableArxiv").checked);
    values.PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR = String($("settingEnableSemanticScholar").checked);
    values.PAPERFLOW_ENABLE_OPENREVIEW = String($("settingEnableOpenReview").checked);
    values.PAPERFLOW_ENABLE_CUSTOM_RSS = String($("settingEnableCustomRss").checked);
    values.PAPERFLOW_CONFERENCE_ACCESS_MODE = document.querySelector('input[name="conferenceAccessMode"]:checked')?.value || "public";
    values.PAPERFLOW_REPORT_STYLE = document.querySelector("[data-pref-mode].active")?.dataset.prefMode || "standard";
    values.PAPERFLOW_WRITE_FEISHU = String($("writeFeishuReports").checked || $("directWriteFeishu").checked || $("directPdfWriteFeishu").checked);
    values.PAPERFLOW_WIKI_INGEST = String($("wikiIngestSetting").checked);
    values.PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW = String($("notesGitLlmReviewSetting")?.checked !== false);
    values.PAPERFLOW_DAILY_LIMIT = $("dailyLimitInput").value;
    values.PAPERFLOW_RELEVANCE_THRESHOLD = $("relevanceThreshold").value;
    values.HTTP_PROXY = $("proxyInput").value;
    values.HTTPS_PROXY = $("proxyInput").value;
    const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ values }) });
    renderSettings(data);
    state.reports = [];
    state.currentReport = null;
    state.wikiNodes = [];
    state.wikiGraph = null;
    state.wikiMap = null;
    state.currentWikiNodeId = "";
    state.currentWikiEditNodeId = "";
    if ($("wikiQuery")) $("wikiQuery").value = "";
    if (state.currentView === "wiki") {
      await loadWiki();
    } else if (state.currentView === "reports") {
      await refreshReports({ keepSelection: false });
    }
    showSettingsMessage(ui().settings.settingsSavedMessage);
    showFeedbackToast("success", ui().settings.save, ui().settings.settingsSavedToast);
  }

  function joinPath(base, suffix) {
    const root = String(base || "").trim().replace(/[\\/]+$/, "");
    if (!root) return "-";
    return `${root}/${suffix}`;
  }

  function updateDerivedNotesPathsPreview() {
    const input = document.querySelector('[data-env-key="PAPERFLOW_NOTES_ROOT_DIR"]');
    const root = input?.value?.trim() || state.settings?.paths?.notes_root_dir || "";
    const currentYear = new Date().getFullYear();
    const derived = {
      pdf: root || "-",
      reports: root || "-",
      wiki: joinPath(root, "wiki"),
      git: joinPath(root, `Daily Note ${currentYear}`)
    };
    Object.entries(derived).forEach(([role, value]) => {
      const target = document.querySelector(`[data-derived-path="${role}"]`);
      if (!target) return;
      if ("value" in target) target.value = value;
      else target.textContent = value;
    });
  }

  async function testProvider(kind) {
    const data = await api("/api/provider-test", { method: "POST", body: JSON.stringify({ kind }) });
    $("providerTestOutput").className = "answer";
    $("providerTestOutput").textContent = JSON.stringify(data, null, 2);
  }

  function showSettingsMessage(message) {
    $("providerTestOutput").className = "answer";
    $("providerTestOutput").textContent = message;
    setStatus(ui().common.updated);
  }

  function addCustomSource() {
    const input = $("sourceUrlInput");
    const value = input.value.trim();
    if (!value) {
      showSettingsMessage(ui().settings.inputUrl);
      return;
    }
    $("customSourcesList").insertAdjacentHTML("beforeend", `
      <div><span>rss</span><strong>${escapeHtml(value)}</strong><button data-remove-source type="button">×</button></div>
    `);
    input.value = "";
    showSettingsMessage(ui().settings.sourceAdded);
  }

  async function exportData(format) {
    const data = await api("/api/export", {
      method: "POST",
      body: JSON.stringify({ user_id: currentUser(), format })
    });
    showSettingsMessage(ui().settings.exported(data.format, data.display_path || data.path, data.count || 0));
  }

  async function saveProfile() {
    const userId = $("profileUserId").value.trim() || currentUser();
    const pdfPaths = $("pdfPaths").value.split(";").map((item) => item.trim()).filter(Boolean);
    const data = await api("/api/profile", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        natural_language: "",
        scholar_url: $("scholarUrl").value,
        homepage_url: $("homepageUrl").value,
        pdf_paths: pdfPaths,
        core_directions_text: $("profileDirectionsInput")?.value || "",
        topic_weights_text: $("profileTopicsInput")?.value || "",
        must_read_keywords: splitListValue($("profileKeywordsInput")?.value || ""),
        must_read_authors: splitListValue($("profileAuthorsInput")?.value || ""),
        must_read_institutions: splitListValue($("profileInstitutionsInput")?.value || ""),
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
    showSettingsMessage(ui().settings.profileLoaded(userId));
  }

  function bindEvents() {
    bindButtonFeedback();
    $("languageSelect")?.addEventListener("change", (event) => setLocale(event.target.value));
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
        startNewChat({ silent: true });
        await loadLatestPush();
        await loadWiki();
        await loadCurrentProfile();
        if (document.querySelector(".view.active")?.id === "chat") {
          await loadChatSessions({ openLatest: true });
        }
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
    $("sortRelevanceBtn")?.addEventListener("click", () => {
      if (!state.push?.papers?.length) {
        showFeedbackToast("warning", ui().papers.noSortableTitle, ui().papers.noSortableDetail);
        return;
      }
      state.push.papers.sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
      renderPush(state.push);
      showFeedbackToast("success", ui().papers.sortedTitle, ui().papers.sortedDetail(state.push.papers.length));
    });
    $("paperList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      const number = Number(button.dataset.number);
      if (button.dataset.action === "read") {
        runAction(() => readSinglePaper(number), "选择精读论文");
        return;
      } else if (button.dataset.action === "skip") {
        setPaperDisposition(number, "skip");
      } else if (button.dataset.action === "later") {
        setPaperDisposition(number, "later");
      }
    });
    $("selectAllSourcesBtn").addEventListener("click", () => {
      toggleAllSources(true);
      showFeedbackToast("success", ui().papers.allSourcesTitle, ui().papers.allSourcesDetail);
    });
    $("clearSourcesBtn").addEventListener("click", () => {
      toggleAllSources(false);
      showFeedbackToast("warning", ui().papers.clearSourcesTitle, ui().papers.clearSourcesDetail);
    });
    document.querySelectorAll("[data-source-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const checkedCount = toggleSourceGroup(button.dataset.sourceToggle);
        const label = button.closest(".source-group")?.querySelector(".source-head strong")?.textContent || ui().common.source;
        showFeedbackToast("success", ui().papers.toggledSourceTitle(label), ui().papers.toggledSourceDetail(checkedCount));
      });
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
        if (href) {
          window.open(href, "_blank", "noopener");
          showFeedbackToast("success", ui().common.openLink, href);
        }
      });
    });
    $("copyReportPathBtn").addEventListener("click", () => runAction(async () => {
      const path = $("copyReportPathBtn").dataset.href || "";
      if (!path) {
        showFeedbackToast("warning", ui().reports.noPathTitle, ui().reports.noPathDetail);
        return;
      }
      if (!navigator.clipboard) throw new Error(ui().common.copyUnsupported);
      await navigator.clipboard.writeText(path);
      showFeedbackToast("success", ui().reports.copiedPath, path);
    }, "复制路径"));
    document.querySelectorAll("[data-annotation-command]").forEach((button) => {
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        applyReportAnnotation(button.dataset.annotationCommand, button.dataset.annotationValue);
      });
    });
    $("clearReportAnnotationsBtn")?.addEventListener("click", clearReportAnnotations);
    document.addEventListener("selectionchange", updateReportAnnotationToolbar);
    $("reportViewerBody").addEventListener("mouseup", () => window.setTimeout(updateReportAnnotationToolbar, 0));
    $("reportViewerBody").addEventListener("keyup", updateReportAnnotationToolbar);
    window.addEventListener("scroll", hideReportAnnotationToolbar, true);
    $("readArxivBtn").addEventListener("click", () => runAction(() => directRead("arxiv"), "生成报告"));
    $("readPdfBtn").addEventListener("click", () => runAction(() => directRead("pdf"), "生成报告"));

    $("refreshWikiBtn").addEventListener("click", () => runAction(refreshWiki, "更新 Wiki"));
    $("syncGithubBtn")?.addEventListener("click", () => runAction(syncGithubNotes, "同步 GitHub"));
    $("wikiSearchBtn").addEventListener("click", () => runAction(searchWiki, "搜索 Wiki"));
    $("wikiDailyScope")?.addEventListener("change", () => {
      const monthInput = $("wikiDailyMonth");
      if (monthInput) monthInput.hidden = $("wikiDailyScope").value !== "month";
      runAction(loadWiki, "更新 Wiki");
    });
    $("wikiDailyMonth")?.addEventListener("change", () => runAction(loadWiki, "更新 Wiki"));
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
      if (state.wikiGraphDragMoved) {
        state.wikiGraphDragMoved = false;
        return;
      }
      if (action) {
        if (action === "zoom-in") zoomWikiGraph(1.25);
        if (action === "zoom-out") zoomWikiGraph(0.8);
        if (action === "focus") {
          resetWikiGraphTransform();
          const focusId = pickWikiFocusNodeId() || "architecture:core";
          const focus = state.wikiMap?.byId?.[focusId] || graphNodesById()[focusId] || state.wikiMap?.byId?.["architecture:core"];
          if (focus) setWikiEntry(rawGraphTitle(focus), rawGraphBody(focus), graphId(focus), { editNodeId: focus.real_node_id || "" });
        }
        return;
      }
      setWikiEntry(
        node.dataset.nodeTitle,
        node.dataset.nodeBody || ui().wiki.architectureClickBody(node.dataset.nodeTitle),
        node.dataset.nodeId || "",
        { editNodeId: node.dataset.realNodeId || "" }
      );
    }, true);
    let wikiGraphDrag = null;
    $("wikiGraph").addEventListener("pointerdown", (event) => {
      if (state.wikiView !== "graph") return;
      if (event.button !== 0) return;
      if (event.target.closest("[data-graph-action], [data-node-title]")) return;
      const canvas = event.target.closest(".graph-canvas");
      if (!canvas) return;
      wikiGraphDrag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        baseX: state.wikiGraphTransform.x,
        baseY: state.wikiGraphTransform.y,
        moved: false
      };
      canvas.classList.add("dragging");
      $("wikiGraph").setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    $("wikiGraph").addEventListener("pointermove", (event) => {
      if (!wikiGraphDrag || wikiGraphDrag.pointerId !== event.pointerId) return;
      const dx = event.clientX - wikiGraphDrag.startX;
      const dy = event.clientY - wikiGraphDrag.startY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) wikiGraphDrag.moved = true;
      state.wikiGraphTransform.x = wikiGraphDrag.baseX + dx;
      state.wikiGraphTransform.y = wikiGraphDrag.baseY + dy;
      applyWikiGraphTransform();
      event.preventDefault();
    });
    const finishWikiGraphDrag = (event) => {
      if (!wikiGraphDrag || wikiGraphDrag.pointerId !== event.pointerId) return;
      state.wikiGraphDragMoved = wikiGraphDrag.moved;
      $("wikiGraph").querySelector(".graph-canvas")?.classList.remove("dragging");
      $("wikiGraph").releasePointerCapture?.(event.pointerId);
      wikiGraphDrag = null;
      window.setTimeout(() => {
        state.wikiGraphDragMoved = false;
      }, 150);
    };
    $("wikiGraph").addEventListener("pointerup", finishWikiGraphDrag);
    $("wikiGraph").addEventListener("pointercancel", finishWikiGraphDrag);
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
          throw new Error(ui().wiki.editNoNode);
        }
        if (!state.currentWikiEditNodeId) {
          throw new Error(ui().wiki.editArchitectureNode);
        }
        editor.value = body.dataset.rawBody || body.textContent;
        editor.hidden = false;
        body.hidden = true;
        $("editWikiEntryBtn").textContent = ui().wiki.save;
      } else {
        const data = await api("/api/wiki/node", {
          method: "POST",
          body: JSON.stringify({
            user_id: currentUser(),
            node_id: state.currentWikiEditNodeId,
            title: $("wikiEntryTitle").dataset.rawTitle || $("wikiEntryTitle").textContent,
            body: editor.value
          })
        });
        const savedTitle = data.node?.title || $("wikiEntryTitle").dataset.rawTitle || $("wikiEntryTitle").textContent;
        const savedBody = data.node?.body || editor.value;
        $("wikiEntryTitle").dataset.rawTitle = savedTitle;
        $("wikiEntryTitle").textContent = localizeWikiText(savedTitle);
        body.dataset.rawBody = savedBody;
        body.innerHTML = renderWikiEntryHtml(localizeWikiText(savedBody));
        if (state.currentWikiEntry) {
          state.currentWikiEntry.title = savedTitle;
          state.currentWikiEntry.body = savedBody;
        }
        body.hidden = false;
        editor.hidden = true;
        $("editWikiEntryBtn").textContent = ui().wiki.edit;
        await loadWiki();
      }
    }, "保存 Wiki"));

    $("wikiAskBtn").addEventListener("click", () => runAction(askWiki, "生成回答"));
    $("newChatBtn").addEventListener("click", () => runAction(() => startNewChat(), "新建对话"));
    $("clearChatHistoryBtn").addEventListener("click", () => runAction(clearChatHistory, "清空历史"));
    $("chatHistoryList").addEventListener("click", (event) => {
      const button = event.target.closest("[data-chat-session-id]");
      if (!button) return;
      runAction(() => loadChatSession(button.dataset.chatSessionId), "打开历史对话");
    });
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
    $("refreshSettingsBtn")?.addEventListener("click", () => runAction(loadSettings, "加载设置"));
    $("saveSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));
    $("saveAdvancedSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));
    $("saveStorageSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));
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
      if (button) {
        const row = button.closest("div");
        const label = row?.querySelector("strong")?.textContent || ui().common.customSource;
        row?.remove();
        showSettingsMessage(ui().settings.sourceRemoved(label));
      }
    });
    document.querySelectorAll("[data-pref-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-pref-mode]").forEach((item) => item.classList.toggle("active", item === button));
        showSettingsMessage(ui().settings.preferenceChanged(button.textContent.trim()));
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
    return inputs.filter((input) => input.checked).length;
  }

  async function init() {
    bindEvents();
    applyLocale();
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
