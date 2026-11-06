/* global window, document, structuredClone */
/* QQ官机群管 · 可视化视图前端
   仅使用原生 ES Module，无构建步骤、无外部 CDN。 */

const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;
const app = document.getElementById("app");
const modalRoot = document.getElementById("modal-root");
const toastRoot = document.getElementById("toast-root");

const PLUGIN_NAME = "astrbot_plugin_qq_group_manage";
const PLUGIN_VERSION = "2.9.4";
const TAB_IDS = ["overview", "pending", "verify", "groups", "settings", "data"];

const TABS = [
  { id: "overview", label: "总览", short: "总览", icon: "layout-dashboard" },
  { id: "pending", label: "入群审批", short: "审批", icon: "inbox", badge: "pending" },
  { id: "verify", label: "进群验证", short: "验证", icon: "badge-check", badge: "verify" },
  { id: "groups", label: "群组", short: "群组", icon: "users" },
  { id: "settings", label: "配置", short: "配置", icon: "settings" },
  { id: "data", label: "数据", short: "数据", icon: "database" },
];

const DEFAULT_THEME_COLOR = "#6d5dfc";
const PRESET_THEMES = [
  { name: "AstrBot 紫", color: "#6d5dfc" },
  { name: "深海蓝", color: "#2f7cf6" },
  { name: "薄荷绿", color: "#0f9f6e" },
  { name: "玫瑰红", color: "#e04458" },
  { name: "琥珀橙", color: "#d97706" },
  { name: "石墨灰", color: "#4a5164" },
];

const ICONS = {
  "layout-dashboard":
    '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  inbox:
    '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  "badge-check":
    '<path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/><path d="m9 12 2 2 4-4"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  settings:
    '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  database:
    '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
  "refresh-cw":
    '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 21H3v-5"/>',
  "alert-triangle":
    '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  "check-circle":
    '<path d="M21.801 10A10 10 0 1 1 17 3.335"/><path d="m9 11 3 3L22 4"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  "x-circle":
    '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  shield:
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  "shield-check":
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  timer:
    '<path d="M10 2h4"/><path d="M12 14v-4"/><circle cx="12" cy="14" r="8"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  "user-plus":
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/>',
  "user-minus":
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 11h-6"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  trash:
    '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  download:
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  "external-link":
    '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  terminal: '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
  bell: '<path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>',
  sparkles:
    '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>',
  gauge: '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
  filter:
    '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
  globe:
    '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  "loader-circle": '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
  "circle-help":
    '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  "file-json":
    '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/><path d="M10 13a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1"/><path d="M14 13a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  "list-filter": '<path d="M3 6h18"/><path d="M7 12h10"/><path d="M10 18h4"/>',
  palette:
    '<circle cx="13.5" cy="6.5" r=".8" fill="currentColor" stroke="none"/><circle cx="17.5" cy="10.5" r=".8" fill="currentColor" stroke="none"/><circle cx="8.5" cy="7.5" r=".8" fill="currentColor" stroke="none"/><circle cx="6.5" cy="12.5" r=".8" fill="currentColor" stroke="none"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>',
  pencil:
    '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  upload:
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
};

function icon(name, size = 18) {
  const span = document.createElement("span");
  span.className = "icon";
  span.style.display = "inline-flex";
  span.style.alignItems = "center";
  span.style.justifyContent = "center";
  span.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;
  return span;
}

const state = {
  tab: "overview",
  context: null,
  themeColor: "",
  overview: null,
  pending: null,
  verifications: null,
  groups: null,
  groupDetail: null,
  selectedGroup: "",
  config: null,
  configScope: "global",
  formValues: {},
  initialValues: {},
  busy: new Set(),
  filters: {
    pendingText: "",
    pendingGroup: "",
    verifyText: "",
    verifyGroup: "",
    groupText: "",
  },
  requestSeq: 0,
};

let modalApi = null;

/* ------------------------------------------------------------------ */
/* 基础工具                                                           */
/* ------------------------------------------------------------------ */

function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    if (child instanceof Node) parent.appendChild(child);
    else parent.appendChild(document.createTextNode(String(child)));
  }
  return parent;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

function button(label, opts = {}, ...children) {
  const node = el(
    "button",
    {
      class: `btn ${opts.className || ""}`.trim(),
      type: opts.type || "button",
      id: opts.id,
      onclick: opts.onClick,
      disabled: opts.disabled,
      title: opts.title,
    },
    ...(children.length ? children : []),
  );
  if (label !== null && label !== undefined) {
    if (children.length === 0) node.textContent = String(label);
  }
  return node;
}

function iconButton(name, label, onClick, extra = {}) {
  return el(
    "button",
    {
      class: `btn ${extra.className || ""}`.trim(),
      type: "button",
      title: label,
      "aria-label": label,
      onclick: onClick,
      disabled: extra.disabled,
    },
    icon(name, extra.size || 15),
    extra.withLabel ? el("span", {}, label) : null,
  );
}

function initials(value) {
  const text = String(value || "").trim();
  return text ? Array.from(text)[0].toUpperCase() : "?";
}

function formatTime(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const now = Date.now();
  const diff = Math.max(0, now - date.getTime());
  if (diff < 60 * 1000) return "刚刚";
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${value} 秒`;
  if (value < 3600) return `${Math.floor(value / 60)} 分钟`;
  if (value < 86400) {
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return minutes ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`;
  }
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  return hours ? `${days} 天 ${hours} 小时` : `${days} 天`;
}

function formatCount(value) {
  const number = Number(value) || 0;
  return number > 9999 ? `${(number / 1000).toFixed(1)}k` : String(number);
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function clone(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value));
}

function tabFromHash() {
  const raw = String(window.location.hash || "").replace(/^#\/?/, "");
  return TAB_IDS.includes(raw) ? raw : "overview";
}

function setHash(tab) {
  try {
    if (window.location.hash !== `#/${tab}`) {
      window.location.hash = `#/${tab}`;
    }
  } catch {
    /* 某些沙盒环境不允许修改 hash，不影响功能 */
  }
}

/* ------------------------------------------------------------------ */
/* 请求与提示                                                         */
/* ------------------------------------------------------------------ */

async function apiGet(endpoint, params) {
  if (!bridge) throw new Error("WebUI bridge 未加载");
  try {
    return await bridge.apiGet(endpoint, params);
  } catch (error) {
    throw new Error(cleanError(error));
  }
}

async function apiPost(endpoint, body) {
  if (!bridge) throw new Error("WebUI bridge 未加载");
  try {
    return await bridge.apiPost(endpoint, body);
  } catch (error) {
    throw new Error(cleanError(error));
  }
}

function cleanError(error) {
  const text = String(error?.message || error || "请求失败");
  return text.replace(/^Error:\s*/i, "").trim() || "请求失败";
}

function toast(message, type = "success", duration = 3600) {
  if (!toastRoot) return;
  const names = {
    success: "check-circle",
    error: "x-circle",
    warning: "alert-triangle",
    info: "info",
  };
  const node = el(
    "div",
    { class: `toast is-${type}`, role: "status" },
    el("span", { class: "toast-icon" }, icon(names[type] || "info", 17)),
    el("div", { class: "toast-copy" }, String(message)),
  );
  toastRoot.appendChild(node);
  window.setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(6px)";
    window.setTimeout(() => node.remove(), 180);
  }, duration);
}

function showModal({
  title,
  description = "",
  iconName = "alert-triangle",
  tone = "",
  body = null,
  confirmText = "确定",
  cancelText = "取消",
  danger = false,
  onConfirm = null,
}) {
  return new Promise((resolve) => {
    if (!modalRoot) {
      resolve(false);
      return;
    }
    closeModal(false);
    const previouslyFocused = document.activeElement;
    const backdrop = el("div", { class: "modal-backdrop" });
    const errorLine = el("p", { class: "modal-error hidden" });
    const confirmButton = button(
      confirmText,
      { className: danger ? "btn-danger-solid" : "btn-primary" },
      danger ? icon("trash", 14) : icon("check", 14),
      el("span", {}, confirmText),
    );
    const cancelButton = button(cancelText, { className: "btn-ghost" });
    const card = el(
      "div",
      {
        class: "modal-card",
        role: "dialog",
        "aria-modal": "true",
        "aria-label": title,
      },
      el(
        "div",
        { class: "modal-head" },
        el(
          "div",
          { class: `modal-icon ${danger ? "is-danger" : ""}` },
          icon(iconName, 19),
        ),
        el(
          "div",
          { style: "min-width:0;flex:1" },
          el("h2", { class: "modal-title" }, title),
          description ? el("p", { class: "modal-desc" }, description) : null,
        ),
        el(
          "button",
          {
            class: "modal-close",
            type: "button",
            "aria-label": "关闭",
            onclick: () => close(false),
          },
          icon("x", 16),
        ),
      ),
      el("div", { class: "modal-body" }, body, errorLine),
      el(
        "div",
        { class: "modal-actions" },
        cancelButton,
        confirmButton,
      ),
    );
    modalRoot.replaceChildren(el("div", { class: "modal-root" }, backdrop, card));

    function close(result) {
      modalRoot.replaceChildren();
      document.removeEventListener("keydown", onKeydown);
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
      if (modalApi && modalApi.close === close) modalApi = null;
      resolve(result);
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
      }
      if (event.key === "Enter" && !event.shiftKey) {
        const target = event.target;
        if (target instanceof HTMLTextAreaElement) return;
        if (target instanceof HTMLElement && target.closest(".modal-card")) {
          event.preventDefault();
          confirmButton.click();
        }
      }
    }

    backdrop.addEventListener("click", () => close(false));
    cancelButton.addEventListener("click", () => close(false));
    confirmButton.addEventListener("click", async () => {
      if (!onConfirm) {
        close(true);
        return;
      }
      confirmButton.disabled = true;
      cancelButton.disabled = true;
      const spinner = el("span", { class: "spinner" });
      const original = confirmButton.innerHTML;
      confirmButton.replaceChildren(spinner, el("span", {}, "处理中…"));
      errorLine.classList.add("hidden");
      try {
        const result = await onConfirm();
        close(result === undefined ? true : result);
      } catch (error) {
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        confirmButton.innerHTML = original;
        errorLine.textContent = cleanError(error);
        errorLine.classList.remove("hidden");
      }
    });

    document.addEventListener("keydown", onKeydown);
    modalApi = { close };
    window.setTimeout(() => confirmButton.focus(), 30);
  });
}

function closeModal(result = false) {
  if (modalApi) {
    const close = modalApi.close;
    modalApi = null;
    close(result);
  }
}

async function confirmAction(title, description, opts = {}) {
  return showModal({
    title,
    description,
    iconName: opts.iconName || "alert-triangle",
    confirmText: opts.confirmText || "确定",
    cancelText: opts.cancelText || "取消",
    danger: Boolean(opts.danger),
    onConfirm: opts.onConfirm || (() => true),
  });
}

async function promptAction(title, description, opts = {}) {
  const input = el("textarea", {
    rows: 3,
    maxlength: 200,
    placeholder: opts.placeholder || "可选，最多 200 个字符",
    style: "min-height:88px",
  });
  return showModal({
    title,
    description,
    iconName: opts.iconName || "x-circle",
    confirmText: opts.confirmText || "确认",
    danger: true,
    body: input,
    onConfirm: () => String(input.value || "").trim(),
  });
}

/* ------------------------------------------------------------------ */
/* 启动与外壳                                                         */
/* ------------------------------------------------------------------ */

async function boot() {
  if (!bridge) {
    renderFatal(
      "未检测到 AstrBot 视图 bridge",
      "请从 AstrBot WebUI → 插件 → QQ官机群管 → 可视化视图打开本页面，不要直接访问 HTML 文件。",
    );
    return;
  }
  try {
    state.context = await Promise.race([
      bridge.ready(),
      new Promise((resolve) => window.setTimeout(() => resolve(null), 2500)),
    ]);
  } catch {
    state.context = null;
  }
  if (state.context) {
    document.title =
      `${state.context.pageTitle || "群管控制台"} · ${state.context.displayName || "QQ官机群管"}`;
  }
  try {
    const preferences = await apiGet("ui/preferences");
    state.themeColor = preferences?.theme_color || "";
  } catch {
    state.themeColor = "";
  }
  applyThemeColor(state.themeColor);
  renderShell();
  bindGlobalEvents();
  try {
    state.overview = await apiGet("overview");
    syncBadges();
  } catch {
    /* 首屏总览失败时仍允许进入其他页签 */
  }
  state.tab = tabFromHash();
  await navigate(state.tab, { updateHash: false });
  window.setInterval(poll, 60_000);
}

function renderFatal(title, message) {
  app.replaceChildren(
    el(
      "div",
      { class: "boot-screen" },
      el("div", { class: "empty-icon" }, icon("alert-triangle", 24)),
      el("h2", { style: "margin:0;color:var(--text)" }, title),
      el("p", { style: "max-width:480px;text-align:center;margin:0" }, message),
      button(
        "重新加载",
        {
          className: "btn-primary",
          onClick: () => window.location.reload(),
        },
        icon("refresh-cw", 14),
        el("span", {}, "重新加载"),
      ),
    ),
  );
}

function renderShell() {
  const context = state.context || {};
  const displayName = context.displayName || "QQ官机群管";
  const pageTitle = context.pageTitle || "群管控制台";
  const subtitle = context.pluginName || PLUGIN_NAME;
  app.replaceChildren(
    el(
      "div",
      { class: "app-shell" },
      el(
        "header",
        { class: "topbar" },
        el(
          "div",
          { class: "topbar-inner" },
          el(
            "div",
            { class: "brand" },
            el(
              "div",
              { class: "brand-logo" },
              el("img", { src: "./assets/logo.png", alt: "" }),
            ),
            el(
              "div",
              { class: "brand-copy" },
              el(
                "h1",
                { class: "brand-title" },
                el("span", { id: "brand-name" }, displayName),
                el("span", { class: "version-pill", id: "version-pill" }, `v${PLUGIN_VERSION}`),
              ),
              el(
                "p",
                { class: "brand-subtitle", id: "brand-subtitle", title: subtitle },
                pageTitle,
              ),
            ),
          ),
          el(
            "div",
            { class: "topbar-actions" },
            el(
              "span",
              { class: "status-pill", id: "status-pill" },
              el("span", { class: "status-dot" }),
              el("span", { id: "status-text" }, "连接中"),
            ),
            iconButton("palette", "更改界面主题色", () => openThemeDialog(), {
              className: "icon-btn",
            }),
            iconButton("refresh-cw", "刷新当前页面", () => refreshCurrent(true), {
              className: "icon-btn",
              id: "refresh-button",
            }),
          ),
        ),
      ),
      el(
        "div",
        { class: "tabs-wrap" },
        el(
          "nav",
          { class: "tabs", "aria-label": "群管控制台导航" },
          ...TABS.map((tab) =>
            el(
              "button",
              {
                class: "tab",
                type: "button",
                title: tab.label,
                "aria-label": tab.label,
                dataset: { tab: tab.id },
                onclick: () => navigate(tab.id),
              },
              icon(tab.icon, 15),
              el("span", { class: "tab-label tab-label-full" }, tab.label),
              el("span", { class: "tab-label tab-label-short" }, tab.short || tab.label),
              tab.badge
                ? el("span", {
                    class: "tab-badge hidden",
                    dataset: { badge: tab.badge },
                  })
                : null,
            ),
          ),
        ),
      ),
      el("main", { class: "page", id: "page", "aria-live": "polite" }),
    ),
  );
  updateActiveTab();
}

function bindGlobalEvents() {
  window.addEventListener("hashchange", () => {
    const tab = tabFromHash();
    if (tab !== state.tab) navigate(tab, { updateHash: false });
  });
  window.addEventListener("beforeunload", (event) => {
    if (!settingsDirty()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  if (bridge?.onContext) {
    bridge.onContext((context) => {
      state.context = { ...(state.context || {}), ...(context || {}) };
      const brand = document.getElementById("brand-name");
      if (brand && context?.displayName) brand.textContent = context.displayName;
      const subtitle = document.getElementById("brand-subtitle");
      if (subtitle && context?.pageTitle) {
        subtitle.textContent = context.pageTitle;
        subtitle.title = context.pluginName || PLUGIN_NAME;
      }
    });
  }
}

function normalizeHexColor(value, fallback = DEFAULT_THEME_COLOR) {
  const text = String(value || "").trim();
  if (/^#[0-9a-f]{6}$/i.test(text)) return text.toLowerCase();
  const rgb = text.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (rgb) {
    return `#${rgb
      .slice(1, 4)
      .map((part) => Number(part).toString(16).padStart(2, "0"))
      .join("")}`;
  }
  return fallback;
}

function currentBrandColor() {
  return normalizeHexColor(
    getComputedStyle(document.documentElement).getPropertyValue("--brand"),
    DEFAULT_THEME_COLOR,
  );
}

function applyThemeColor(color) {
  const root = document.documentElement;
  if (color) root.style.setProperty("--brand", color);
  else root.style.removeProperty("--brand");
}

async function openThemeDialog() {
  const previous = state.themeColor || "";
  let draft = previous;
  const colorInput = el("input", {
    type: "color",
    value: previous || currentBrandColor(),
    "aria-label": "自定义主题色",
  });
  const colorValue = el("span", { class: "theme-color-value" });
  const preview = el(
    "div",
    { class: "theme-preview" },
    el(
      "div",
      {},
      el("p", { class: "theme-preview-title" }, "主色预览"),
      el("p", { class: "theme-preview-sub" }, "按钮、标签、强调色会同步变化"),
    ),
    el("span", { class: "btn btn-white btn-sm" }, "示例按钮"),
  );
  const swatches = PRESET_THEMES.map((preset) => {
    const swatch = el("button", {
      class: "theme-swatch",
      type: "button",
      title: preset.name,
      "aria-label": preset.name,
      style: `background:${preset.color}`,
      onclick: () => setDraft(preset.color),
    });
    swatch.dataset.color = preset.color;
    return swatch;
  });

  function setDraft(color) {
    draft = color ? normalizeHexColor(color) : "";
    colorInput.value = draft || currentBrandColor();
    colorValue.textContent = draft ? draft.toUpperCase() : "跟随默认主题";
    swatches.forEach((swatch) => {
      swatch.classList.toggle("is-active", swatch.dataset.color === draft);
    });
    applyThemeColor(draft);
  }

  colorInput.addEventListener("input", () => setDraft(colorInput.value));
  setDraft(draft);

  const body = el(
    "div",
    { class: "theme-dialog" },
    el(
      "p",
      { class: "theme-tip" },
      "选择预设，或用取色器自定义。保存后会写入插件数据目录，下次打开自动恢复。建议选择中深色，保证按钮文字对比度。",
    ),
    el("div", { class: "theme-swatches" }, ...swatches),
    el(
      "div",
      { class: "theme-custom" },
      colorInput,
      colorValue,
      button(
        "恢复默认",
        {
          className: "btn btn-ghost btn-sm",
          onClick: () => setDraft(""),
        },
        icon("refresh-cw", 13),
        el("span", {}, "恢复默认"),
      ),
    ),
    preview,
  );

  const saved = await showModal({
    title: "更改界面主题色",
    description: "只改变这个控制台的强调色，不影响 AstrBot 其他页面。",
    iconName: "palette",
    confirmText: "保存主题",
    body,
    onConfirm: async () => {
      const result = await apiPost("ui/preferences/save", {
        theme_color: draft,
      });
      state.themeColor = result?.theme_color || "";
      applyThemeColor(state.themeColor);
      toast("主题色已更新");
      return true;
    },
  });
  if (!saved) applyThemeColor(previous);
}

function updateActiveTab() {
  document.querySelectorAll("[data-tab]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.tab === state.tab);
  });
}

function updateStatusPill() {
  const pill = document.getElementById("status-pill");
  const text = document.getElementById("status-text");
  if (!pill || !text) return;
  if (!state.overview) {
    text.textContent = "连接中";
    pill.title = "连接中";
    pill.classList.remove("is-warn");
    return;
  }
  const runtime = state.overview.runtime || {};
  const online = Number(runtime.online_platform_count || 0);
  if (online > 0) {
    text.textContent = runtime.per_group ? "运行中 · 分群模式" : "运行中 · 全局模式";
    pill.classList.remove("is-warn");
  } else {
    text.textContent = "平台离线";
    pill.classList.add("is-warn");
  }
  pill.title = text.textContent;
}

function setBadge(name, count) {
  const node = document.querySelector(`[data-badge="${name}"]`);
  if (!node) return;
  const number = Number(count) || 0;
  node.textContent = formatCount(number);
  node.classList.toggle("hidden", number <= 0);
  node.classList.toggle("is-hot", number > 0);
}

function syncBadges() {
  const runtime = state.overview?.runtime;
  const pendingCount =
    state.pending?.total ?? runtime?.pending_count ?? 0;
  const verifyCount =
    state.verifications?.total ?? runtime?.verification_count ?? 0;
  setBadge("pending", pendingCount);
  setBadge("verify", verifyCount);
  updateStatusPill();
}

function setRefreshSpinning(spinning) {
  const node = document.getElementById("refresh-button");
  if (node) node.classList.toggle("is-spinning", Boolean(spinning));
}

/* ------------------------------------------------------------------ */
/* 路由与加载                                                         */
/* ------------------------------------------------------------------ */

async function navigate(tab, opts = {}) {
  if (!TAB_IDS.includes(tab)) tab = "overview";
  if (tab === state.tab && tab === "settings" && settingsDirty()) return;
  if (state.tab === "settings" && tab !== "settings" && settingsDirty()) {
    const stay = await confirmAction(
      "离开配置页面？",
      "当前有未保存的配置修改，离开后将丢失这些修改。",
      { confirmText: "仍然离开", danger: true },
    );
    if (!stay) return;
  }
  state.tab = tab;
  if (opts.updateHash !== false) setHash(tab);
  updateActiveTab();
  window.scrollTo({ top: 0, behavior: "smooth" });
  renderLoading();
  try {
    await loadTab(tab);
  } catch (error) {
    renderError(error);
  }
}

async function loadTab(tab) {
  const seq = ++state.requestSeq;
  if (tab === "overview") {
    const data = await apiGet("overview");
    if (seq !== state.requestSeq) return;
    state.overview = data;
    syncBadges();
    renderOverview();
    return;
  }
  if (tab === "pending") {
    const data = await apiGet("pending");
    if (seq !== state.requestSeq) return;
    state.pending = data;
    syncBadges();
    renderPending();
    return;
  }
  if (tab === "verify") {
    const data = await apiGet("verifications");
    if (seq !== state.requestSeq) return;
    state.verifications = data;
    syncBadges();
    renderVerify();
    return;
  }
  if (tab === "groups") {
    const data = await apiGet("groups");
    if (seq !== state.requestSeq) return;
    state.groups = data;
    if (!state.selectedGroup || !data.items.some((item) => item.umo === state.selectedGroup)) {
      state.selectedGroup = data.items[0]?.umo || "";
    }
    renderGroups();
    if (state.selectedGroup) await loadGroupDetail(state.selectedGroup, seq);
    return;
  }
  if (tab === "settings") {
    if (!state.groups) {
      try {
        state.groups = await apiGet("groups");
      } catch {
        state.groups = { items: [] };
      }
    }
    if (state.configScope === "group" && !state.selectedGroup) {
      state.selectedGroup = state.groups.items?.[0]?.umo || "";
    }
    const umo = state.configScope === "group" ? state.selectedGroup : "";
    const data = await apiGet("config", umo ? { umo } : undefined);
    if (seq !== state.requestSeq) return;
    applyConfigData(data);
    renderSettings();
    return;
  }
  if (tab === "data") {
    if (!state.overview) {
      const data = await apiGet("overview");
      if (seq !== state.requestSeq) return;
      state.overview = data;
      syncBadges();
    }
    renderData();
  }
}

async function refreshCurrent(showToast = false, silent = false) {
  if (state.busy.size > 0) return;
  if (state.tab === "settings" && settingsDirty()) {
    const ok = await confirmAction(
      "刷新配置页面？",
      "当前有未保存的配置修改，刷新后将丢失这些修改。",
      { confirmText: "仍然刷新", danger: true },
    );
    if (!ok) return;
  }
  if (!silent) setRefreshSpinning(true);
  try {
    await loadTab(state.tab);
    if (showToast) toast("已刷新", "success", 1800);
  } catch (error) {
    if (!silent) toast(cleanError(error), "error");
  } finally {
    setRefreshSpinning(false);
  }
}

async function refreshOverviewSilent() {
  try {
    state.overview = await apiGet("overview");
    syncBadges();
    if (state.tab === "overview") renderOverview();
  } catch {
    /* 统计刷新失败不影响当前操作结果 */
  }
}

async function poll() {
  if (document.visibilityState !== "visible") return;
  if (!["overview", "pending", "verify"].includes(state.tab)) return;
  if (state.busy.size > 0 || modalApi) return;
  const active = document.activeElement;
  if (
    active &&
    ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName) &&
    active.closest(".toolbar")
  ) {
    return;
  }
  try {
    await loadTab(state.tab);
  } catch {
    /* 轮询失败不打扰用户 */
  }
}

function renderLoading() {
  const page = document.getElementById("page");
  if (!page) return;
  const cards = [];
  for (let index = 0; index < (state.tab === "settings" ? 4 : 3); index += 1) {
    cards.push(el("div", { class: "skeleton skeleton-card" }));
  }
  page.replaceChildren(
    el(
      "div",
      { class: "stack" },
      el("div", { class: "skeleton", style: "height:132px;border-radius:22px" }),
      el("div", { class: "skeleton", style: "height:76px;border-radius:15px" }),
      ...cards,
    ),
  );
}

function renderError(error) {
  const page = document.getElementById("page");
  if (!page) return;
  page.replaceChildren(
    el(
      "div",
      { class: "card" },
      el(
        "div",
        { class: "empty" },
        el("div", { class: "empty-icon" }, icon("alert-triangle", 23)),
        el("h3", {}, "加载失败"),
        el("p", {}, cleanError(error)),
        button("重试", {
          className: "btn-primary",
          onClick: () => refreshCurrent(false),
        }),
      ),
    ),
  );
}

/* ------------------------------------------------------------------ */
/* 总览                                                               */
/* ------------------------------------------------------------------ */

function renderOverview() {
  const data = state.overview;
  if (!data) return renderLoading();
  const page = document.getElementById("page");
  const runtime = data.runtime || {};
  const features = data.features || [];
  const groups = data.groups || [];
  const pending = data.pending || [];
  const verifications = data.verifications || [];
  const health = data.health || [];

  const hero = el(
    "section",
    { class: "hero" },
    el(
      "div",
      { class: "hero-copy" },
      el(
        "span",
        { class: "eyebrow" },
        icon("sparkles", 13),
        "QQ 官方机器人 · 群管理",
      ),
      el("h1", {}, "群管控制台"),
      el(
        "p",
        {},
        runtime.per_group
          ? "当前使用分群配置：每个群可以拥有独立的开关、词表与安全限制。"
          : "当前使用全局配置：所有群共享同一套群管开关与安全限制。",
        runtime.pending_count
          ? ` 有 ${runtime.pending_count} 条入群申请等待处理。`
          : " 暂无待处理申请。",
      ),
      el(
        "div",
        { class: "hero-actions" },
        button(
          "处理入群申请",
          {
            className: "btn-white",
            onClick: () => navigate("pending"),
          },
          icon("inbox", 15),
          el("span", {}, "处理入群申请"),
        ),
        button(
          "查看验证队列",
          {
            className: "btn-ghost",
            onClick: () => navigate("verify"),
          },
          icon("badge-check", 15),
          el("span", {}, "查看验证队列"),
        ),
        button(
          "编辑配置",
          {
            className: "btn-ghost",
            onClick: () => navigate("settings"),
          },
          icon("settings", 15),
          el("span", {}, "编辑配置"),
        ),
      ),
    ),
    el(
      "div",
      { class: "hero-side" },
      el(
        "div",
        { class: "hero-orbit" },
        el("span", { class: "hero-orbit-dot" }),
        el("span", { class: "hero-orbit-dot" }),
        el("span", { class: "hero-orbit-dot" }),
        el("div", { class: "hero-orbit-center" }, icon("shield-check", 36)),
      ),
    ),
  );

  const stats = el(
    "section",
    { class: "stat-grid" },
    statCard(
      "inbox",
      "待审申请",
      runtime.pending_count,
      runtime.pending_count ? "需要人工处理" : "队列已清空",
      "",
    ),
    statCard(
      "badge-check",
      "未完成验证",
      runtime.verification_count,
      runtime.enabled_verify_groups
        ? `${runtime.enabled_verify_groups} 个群已开启验证`
        : "未开启进群验证",
      "is-warning",
    ),
    statCard(
      "users",
      "已接入群",
      runtime.group_count,
      runtime.per_group ? "分群配置已启用" : "全局配置模式",
      "is-info",
    ),
    statCard(
      "shield",
      "插件群管",
      runtime.admin_count,
      "由插件额外授权",
      "is-success",
    ),
  );

  const featureCard = el(
    "section",
    { class: "card" },
    cardHead(
      "sparkles",
      "功能开关",
      "所有群管能力的当前生效状态",
      button("去配置", {
        className: "card-link",
        onClick: () => navigate("settings"),
      }),
    ),
    el("div", { class: "card-body" }, featureBoard(features)),
  );

  const pendingCard = el(
    "section",
    { class: "card" },
    cardHead(
      "inbox",
      "最新入群申请",
      pending.length ? `显示最近 ${pending.length} 条` : "暂无待处理申请",
      button("全部", {
        className: "card-link",
        onClick: () => navigate("pending"),
      }),
    ),
    el(
      "div",
      { class: "card-body" },
      pending.length
        ? el(
            "div",
            { class: "mini-queue" },
            ...pending.map((item) =>
              el(
                "button",
                {
                  class: "mini-item",
                  type: "button",
                  style: "width:100%;background:none;border:0;text-align:left;cursor:pointer",
                  onClick: () => navigate("pending"),
                },
                el("span", { class: "mini-avatar" }, initials(item.nickname)),
                el(
                  "span",
                  { class: "mini-copy" },
                  el("p", { class: "mini-title" }, item.nickname),
                  el("p", { class: "mini-sub" }, item.group_label),
                ),
                el("span", { class: "mini-time" }, formatTime(item.stored_at)),
              ),
            ),
          )
        : emptyInline("inbox", "队列已清空", "新的入群申请会出现在这里。"),
    ),
  );

  const verifyCard = el(
    "section",
    { class: "card" },
    cardHead(
      "badge-check",
      "进群验证",
      verifications.length ? `待处理 ${verifications.length} 人` : "暂无待处理验证",
      button("全部", {
        className: "card-link",
        onClick: () => navigate("verify"),
      }),
    ),
    el(
      "div",
      { class: "card-body" },
      verifications.length
        ? el(
            "div",
            { class: "mini-queue" },
            ...verifications.map((item) =>
              el(
                "button",
                {
                  class: "mini-item",
                  type: "button",
                  style: "width:100%;background:none;border:0;text-align:left;cursor:pointer",
                  onClick: () => navigate("verify"),
                },
                el(
                  "span",
                  { class: "mini-avatar" },
                  item.status === "failed" ? icon("x", 15) : initials(item.member_short),
                ),
                el(
                  "span",
                  { class: "mini-copy" },
                  el("p", { class: "mini-title" }, item.member_short),
                  el(
                    "p",
                    { class: "mini-sub" },
                    item.status === "failed"
                      ? "验证失败，等待管理员处理"
                      : item.remaining_seconds
                        ? `剩余 ${formatDuration(item.remaining_seconds)}`
                        : "等待作答",
                  ),
                ),
                el(
                  "span",
                  { class: "mini-time" },
                  item.status === "failed" ? "失败" : `${item.failures}/${item.max_failures}`,
                ),
              ),
            ),
          )
        : emptyInline("badge-check", "暂无验证", "新成员进群并开启验证后会出现在这里。"),
    ),
  );

  const groupsCard = el(
    "section",
    { class: "card" },
    cardHead(
      "users",
      "群组概览",
      groups.length ? `共 ${runtime.group_count} 个群` : "尚未发现群组",
      button("查看全部", {
        className: "card-link",
        onClick: () => navigate("groups"),
      }),
    ),
    el(
      "div",
      { class: "card-body" },
      groups.length
        ? el(
            "div",
            { class: "mini-queue" },
            ...groups.slice(0, 6).map((group) =>
              el(
                "button",
                {
                  class: "mini-item",
                  type: "button",
                  style: "width:100%;background:none;border:0;text-align:left;cursor:pointer",
                  onClick: () => {
                    state.selectedGroup = group.umo;
                    navigate("groups");
                  },
                },
                el(
                  "span",
                  { class: "mini-avatar" },
                  icon(group.profile?.exists ? "shield-check" : "globe", 15),
                ),
                el(
                  "span",
                  { class: "mini-copy" },
                  el("p", { class: "mini-title" }, group.note || group.label),
                  el("p", { class: "mini-sub mono" }, group.umo),
                ),
                el(
                  "span",
                  { class: "mini-time" },
                  group.pending_count
                    ? `${group.pending_count} 待审`
                    : group.verification_count
                      ? `${group.verification_count} 验证`
                      : group.profile?.exists
                        ? "已配置"
                        : group.last_seen
                          ? formatTime(group.last_seen)
                          : "继承全局",
                ),
              ),
            ),
          )
        : emptyInline("users", "暂无群组", "群消息、入群申请、验证或群管操作后会记录群组。"),
    ),
  );

  const healthCard = el(
    "section",
    { class: "card" },
    cardHead("shield", "运行状态", "快速检查关键依赖", null),
    el(
      "div",
      { class: "card-body" },
      el(
        "div",
        { class: "health-list" },
        ...health.map((item) =>
          el(
            "div",
            { class: "health-item" },
            el(
              "span",
              { class: `health-icon is-${item.status === "ok" ? "" : item.status}` },
              icon(item.status === "ok" ? "check" : item.status === "warn" ? "alert-triangle" : "info", 14),
            ),
            el(
              "div",
              { class: "health-copy" },
              el("p", { class: "health-label" }, item.label),
              el("p", { class: "health-detail" }, item.detail),
            ),
          ),
        ),
      ),
    ),
  );

  const runtimeCard = el(
    "section",
    { class: "card" },
    cardHead("gauge", "运行参数", "当前插件实例的关键信息", null),
    el(
      "div",
      { class: "card-body" },
      el(
        "div",
        { class: "kv-list" },
        kvRow("插件版本", `v${data.plugin?.version || PLUGIN_VERSION}`),
        kvRow("配置模式", runtime.per_group ? "分群配置" : "全局配置"),
        kvRow("配置布局", `v${runtime.config_layout_version ?? 0}`),
        kvRow(
          "QQ 平台",
          `${runtime.online_platform_count || 0}/${(runtime.platforms || []).length} 在线`,
        ),
        kvRow("数据保留", `${runtime.retention_days || 30} 天`),
        kvRow("视图 API", state.overview ? "已连接" : "未连接"),
      ),
    ),
  );

  page.replaceChildren(
    hero,
    stats,
    el(
      "div",
      { class: "layout-2" },
      el("div", { class: "stack" }, featureCard, el("div", { class: "queue-grid" }, pendingCard, verifyCard), groupsCard),
      el("div", { class: "stack" }, healthCard, runtimeCard),
    ),
    footer(),
  );
}

function statCard(iconName, label, value, hint, tone) {
  return el(
    "article",
    { class: "stat-card" },
    el("div", { class: `stat-icon ${tone || ""}` }, icon(iconName, 18)),
    el(
      "div",
      { class: "stat-copy" },
      el("p", { class: "stat-label" }, label),
      el("p", { class: "stat-value" }, formatCount(value)),
      el("p", { class: "stat-hint" }, hint),
    ),
  );
}

function cardHead(iconName, title, subtitle, action) {
  return el(
    "div",
    { class: "card-head" },
    el("div", { class: "card-head-icon" }, icon(iconName, 16)),
    el(
      "div",
      { class: "card-head-copy" },
      el("h2", { class: "card-title" }, title),
      subtitle ? el("p", { class: "card-subtitle" }, subtitle) : null,
    ),
    action,
  );
}

function featureBoard(features) {
  const groups = new Map();
  for (const feature of features) {
    if (!groups.has(feature.category)) groups.set(feature.category, []);
    groups.get(feature.category).push(feature);
  }
  if (!groups.size) return emptyInline("sparkles", "暂无功能数据", "插件加载后可查看功能状态。");
  return el(
    "div",
    { class: "feature-wrap" },
    ...Array.from(groups.entries()).map(([category, items]) =>
      el(
        "div",
        { class: "feature-group" },
        el("p", { class: "feature-group-title" }, category),
        el(
          "div",
          { class: "feature-chips" },
          ...items.map((feature) =>
            el(
              "span",
              { class: `feature-chip ${feature.enabled ? "is-on" : ""}` },
              el("span", { class: "feature-chip-dot" }),
              feature.name,
            ),
          ),
        ),
      ),
    ),
  );
}

function emptyInline(iconName, title, description) {
  return el(
    "div",
    { class: "empty", style: "padding:26px 14px" },
    el("div", { class: "empty-icon", style: "width:42px;height:42px;border-radius:12px" }, icon(iconName, 19)),
    el("h3", {}, title),
    el("p", {}, description),
  );
}

function kvRow(key, value) {
  return el(
    "div",
    { class: "kv-row" },
    el("span", { class: "kv-key" }, key),
    el("span", { class: "kv-value", title: String(value) }, String(value)),
  );
}

function footer() {
  return el(
    "footer",
    { class: "footer" },
    el("span", {}, "QQ官机群管 · WebUI 视图"),
    el("span", { class: "dot-sep" }, "·"),
    el("span", {}, `v${PLUGIN_VERSION}`),
    el("span", { class: "dot-sep" }, "·"),
    el("span", {}, "数据仅在 AstrBot 本地处理"),
    el("span", { class: "dot-sep" }, "·"),
    el(
      "span",
      {},
      "插件作者：",
      el(
        "a",
        {
          class: "footer-link",
          href: "https://github.com/1023286457",
          target: "_blank",
          rel: "noopener noreferrer",
        },
        "简单么么熊",
      ),
    ),
    el("span", { class: "dot-sep" }, "·"),
    el("span", {}, "QQ：1023286457"),
    el("span", { class: "dot-sep" }, "·"),
    el("span", {}, "QQ群：1081896895"),
  );
}

/* ------------------------------------------------------------------ */
/* 入群审批                                                           */
/* ------------------------------------------------------------------ */

function renderPending() {
  const data = state.pending || { items: [], total: 0 };
  const items = data.items || [];
  const page = document.getElementById("page");
  const groups = uniqueGroups(items);
  if (
    state.filters.pendingGroup &&
    !groups.some(([value]) => value === state.filters.pendingGroup)
  ) {
    state.filters.pendingGroup = "";
  }

  const list = el("div", { class: "queue-list", id: "pending-list" });
  const count = el("span", { id: "pending-count" }, `${items.length} 条待处理`);
  const search = el("input", {
    type: "search",
    placeholder: "搜索昵称或群组",
    value: state.filters.pendingText,
    oninput: (event) => {
      state.filters.pendingText = event.target.value;
      renderPendingList();
    },
  });
  const groupSelect = el(
    "select",
    {
      class: "select",
      onchange: (event) => {
        state.filters.pendingGroup = event.target.value;
        renderPendingList();
      },
    },
    el("option", { value: "" }, "全部群组"),
    ...groups.map(([value, label]) => el("option", { value }, label)),
  );
  groupSelect.value = state.filters.pendingGroup;

  page.replaceChildren(
    el(
      "div",
      { class: "toolbar" },
      el("h2", { class: "toolbar-title" }, "入群审批", count),
      el("div", { class: "search" }, icon("search", 14), search),
      groupSelect,
      iconButton("refresh-cw", "刷新", () => refreshCurrent(true)),
    ),
    list,
    footer(),
  );
  renderPendingList();
}

function renderPendingList() {
  const container = document.getElementById("pending-list");
  if (!container) return;
  const all = state.pending?.items || [];
  const text = state.filters.pendingText.trim().toLowerCase();
  const group = state.filters.pendingGroup;
  const items = all.filter((item) => {
    if (group && item.group_umo !== group) return false;
    if (!text) return true;
    return `${item.nickname} ${item.group_label} ${item.source}`
      .toLowerCase()
      .includes(text);
  });
  const count = document.getElementById("pending-count");
  if (count) count.textContent = `${items.length} 条待处理`;
  if (!items.length) {
    container.replaceChildren(
      el(
        "div",
        { class: "card" },
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty-icon" }, icon("inbox", 24)),
          el("h3", {}, all.length ? "没有匹配的申请" : "所有申请都处理完了"),
          el("p", {}, all.length ? "调整搜索或群组筛选后再试。" : "新的入群申请会自动出现在这里。"),
        ),
      ),
    );
    return;
  }
  container.replaceChildren(...items.map((item) => pendingCard(item)));
}

function pendingCard(item) {
  const busy = state.busy.has(item.id);
  const hasDetails =
    Boolean(item.verify_message) ||
    Boolean(item.risk_tips) ||
    (item.questions || []).length > 0;
  const details = el(
    "div",
    { class: "queue-detail hidden" },
    item.verify_message ? el("div", {}, `验证消息：${item.verify_message}`) : null,
    ...(item.questions || []).map((qa) =>
      el(
        "div",
        { style: "margin-top:4px" },
        el("span", { class: "muted" }, `问：${qa.question || "（无问题）"}`),
        el("br"),
        el("span", {}, `答：${qa.answer || "（未回答）"}`),
      ),
    ),
    item.risk_tips ? el("div", { class: "tag is-warning" }, `风险提示：${item.risk_tips}`) : null,
  );
  const expand = hasDetails
    ? el(
        "button",
        {
          class: "queue-expand",
          type: "button",
          onclick: () => {
            const hidden = details.classList.toggle("hidden");
            expand.textContent = hidden ? "展开详情" : "收起详情";
          },
        },
        "展开详情",
      )
    : null;
  return el(
    "article",
    { class: "queue-card" },
    el("div", { class: "queue-avatar" }, initials(item.nickname)),
    el(
      "div",
      { class: "queue-main" },
      el(
        "div",
        { class: "queue-head" },
        el("h3", { class: "queue-name" }, item.nickname || "未提供昵称"),
        el("span", { class: "tag is-brand" }, item.source || "未知来源"),
        item.risk_tips ? el("span", { class: "tag is-warning" }, "风险提示") : null,
        item.can_review ? null : el("span", { class: "tag is-danger" }, "平台离线"),
      ),
      el(
        "div",
        { class: "meta-line" },
        el("span", {}, item.group_label),
        el("span", {}, formatTime(item.apply_at || item.stored_at)),
        item.questions?.length
          ? el("span", {}, `${item.questions.length} 个入群问题`)
          : el("span", {}, "无入群问题"),
      ),
      item.questions?.length
        ? el(
            "div",
            { class: "qa-preview" },
            ...item.questions.slice(0, 2).map((qa) =>
              el(
                "div",
                { class: "qa-row" },
                el("span", { class: "qa-label" }, "问"),
                el(
                  "span",
                  { class: "qa-text" },
                  `${qa.question || "（无问题）"}`,
                  el("br"),
                  el("span", { class: "muted" }, `答：${qa.answer || "（未回答）"}`),
                ),
              ),
            ),
          )
        : null,
      details,
      expand,
    ),
    el(
      "div",
      { class: "queue-actions" },
      button(
        "拒绝",
        {
          className: "btn-danger btn-sm",
          disabled: busy || !item.can_review,
          onClick: () => declinePending(item),
        },
        icon("x", 13),
        el("span", {}, "拒绝"),
      ),
      button(
        "同意",
        {
          className: "btn-success btn-sm",
          disabled: busy || !item.can_review,
          onClick: () => approvePending(item),
        },
        busy ? el("span", { class: "spinner" }) : icon("check", 13),
        el("span", {}, busy ? "处理中" : "同意"),
      ),
    ),
  );
}

async function approvePending(item) {
  const ok = await confirmAction(
    "同意入群申请",
    `确认同意 ${item.nickname || "该用户"} 加入 ${item.group_label}？审批结果会直接提交到 QQ。`,
    { iconName: "user-plus", confirmText: "同意入群" },
  );
  if (!ok) return;
  await runPendingAction(item, "approve");
}

async function declinePending(item) {
  const reason = await promptAction(
    "拒绝入群申请",
    `填写拒绝理由（可留空），将直接提交到 QQ：${item.nickname || "该用户"} · ${item.group_label}`,
    { confirmText: "拒绝申请", placeholder: "例如：答案与群主题无关" },
  );
  if (reason === false) return;
  await runPendingAction(item, "decline", reason);
}

async function runPendingAction(item, action, reason = "") {
  state.busy.add(item.id);
  renderPendingList();
  try {
    const result = await apiPost("pending/review", {
      id: item.id,
      action,
      reason: reason || "",
    });
    toast(result?.message || (action === "approve" ? "已同意入群申请" : "已拒绝入群申请"));
    if (state.tab === "pending") await loadTab("pending");
    await refreshOverviewSilent();
    syncBadges();
  } catch (error) {
    toast(cleanError(error), "error", 5000);
  } finally {
    state.busy.delete(item.id);
    if (state.tab === "pending") renderPendingList();
  }
}

/* ------------------------------------------------------------------ */
/* 进群验证                                                           */
/* ------------------------------------------------------------------ */

function renderVerify() {
  const data = state.verifications || { items: [], total: 0 };
  const items = data.items || [];
  const page = document.getElementById("page");
  const groups = uniqueGroups(items);
  if (
    state.filters.verifyGroup &&
    !groups.some(([value]) => value === state.filters.verifyGroup)
  ) {
    state.filters.verifyGroup = "";
  }
  const count = el("span", { id: "verify-count" }, `${items.length} 人待处理`);
  const search = el("input", {
    type: "search",
    placeholder: "搜索成员或群组",
    value: state.filters.verifyText,
    oninput: (event) => {
      state.filters.verifyText = event.target.value;
      renderVerifyList();
    },
  });
  const groupSelect = el(
    "select",
    {
      class: "select",
      onchange: (event) => {
        state.filters.verifyGroup = event.target.value;
        renderVerifyList();
      },
    },
    el("option", { value: "" }, "全部群组"),
    ...groups.map(([value, label]) => el("option", { value }, label)),
  );
  groupSelect.value = state.filters.verifyGroup;

  page.replaceChildren(
    el(
      "div",
      { class: "toolbar" },
      el("h2", { class: "toolbar-title" }, "进群验证", count),
      el("div", { class: "search" }, icon("search", 14), search),
      groupSelect,
      button(
        "一键通过所有验证",
        { className: "btn-primary btn-sm", onClick: () => releaseAllVerifications() },
        icon("badge-check", 14),
        el("span", {}, "一键通过所有验证"),
      ),
      iconButton("refresh-cw", "刷新", () => refreshCurrent(true)),
    ),
    el("div", { class: "verify-grid", id: "verify-list" }),
    footer(),
  );
  renderVerifyList();
}

function filteredVerifications() {
  const all = state.verifications?.items || [];
  const text = state.filters.verifyText.trim().toLowerCase();
  const group = state.filters.verifyGroup;
  return all.filter((item) => {
    if (group && item.group_umo !== group) return false;
    if (!text) return true;
    return `${item.member_openid} ${item.member_short} ${item.group_label} ${item.question}`
      .toLowerCase()
      .includes(text);
  });
}

async function releaseAllVerifications() {
  const items = filteredVerifications();
  if (!items.length) {
    toast("当前筛选下没有待处理的验证", "warning");
    return;
  }
  const ok = await confirmAction(
    "一键通过所有验证",
    `确认通过当前筛选的 ${items.length} 名成员？验证失败被禁言的成员会同时尝试解禁；该操作不会影响其他筛选范围外的记录。`,
    { iconName: "badge-check", confirmText: "全部通过" },
  );
  if (!ok) return;
  try {
    const result = await apiPost(
      "verifications/release-all",
      { ids: items.map((item) => item.id) },
    );
    toast(result?.message || `已放行 ${result?.released || 0} 人`);
    await refreshCurrent(true);
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

function renderVerifyList() {
  const container = document.getElementById("verify-list");
  if (!container) return;
  const all = state.verifications?.items || [];
  const items = filteredVerifications();
  const count = document.getElementById("verify-count");
  if (count) count.textContent = `${items.length} 人待处理`;
  if (!items.length) {
    container.replaceChildren(
      el(
        "div",
        { class: "card", style: "grid-column:1/-1" },
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty-icon" }, icon("badge-check", 24)),
          el("h3", {}, all.length ? "没有匹配的验证" : "没有待处理的进群验证"),
          el("p", {}, all.length ? "调整搜索或群组筛选后再试。" : "新成员进群并开启验证后会出现在这里。"),
        ),
      ),
    );
    return;
  }
  container.replaceChildren(...items.map((item) => verifyCard(item)));
}

function verifyCard(item) {
  const busy = state.busy.has(item.id);
  const failed = item.status === "failed";
  const countdown = failed
    ? "等待管理员处理"
    : item.remaining_seconds
      ? `剩余 ${formatDuration(item.remaining_seconds)}`
      : item.expired
        ? "已超时"
        : "等待作答";
  return el(
    "article",
    { class: `verify-card ${failed ? "is-failed" : ""}` },
    el(
      "div",
      { class: "verify-head" },
      el("div", { class: "queue-avatar" }, failed ? icon("x", 16) : initials(item.member_short)),
      el(
        "div",
        { class: "verify-member" },
        el("p", { class: "verify-name" }, item.member_short || item.member_openid),
        el(
          "p",
          { class: "meta-line", style: "margin-top:0" },
          el("span", {}, item.group_label),
          el("span", {}, item.mode_label),
        ),
      ),
      el(
        "span",
        { class: `tag ${failed ? "is-danger" : item.expired ? "is-warning" : "is-info"}` },
        item.status_label,
      ),
    ),
    el("div", { class: "verify-question" }, item.question || "（题目为空）"),
    el(
      "div",
      { class: "verify-meta" },
      el("span", {}, `答错 ${item.failures}/${item.max_failures} 次`),
      el("span", {}, countdown),
      el("span", {}, item.delivered ? "题目已送达" : "题目未送达"),
      item.timeout_handled ? el("span", {}, "超时已处理") : null,
      item.can_act ? null : el("span", { class: "tag is-danger" }, "平台离线"),
    ),
    el(
      "div",
      { class: "verify-actions" },
      button(
        "放行",
        {
          className: "btn-success btn-sm",
          disabled: busy || !item.can_act,
          onClick: () => releaseVerification(item),
        },
        busy ? el("span", { class: "spinner" }) : icon("check", 13),
        el("span", {}, "放行"),
      ),
      button(
        "重新出题",
        {
          className: "btn-sm",
          disabled: busy || !item.can_act,
          onClick: () => retryVerification(item),
        },
        icon("refresh-cw", 13),
        el("span", {}, "重新出题"),
      ),
    ),
  );
}

async function releaseVerification(item) {
  const ok = await confirmAction(
    "放行该成员",
    item.status === "failed"
      ? `确认放行 ${item.member_short}？该成员当前处于验证失败状态，放行时会尝试解除禁言。`
      : `确认放行 ${item.member_short}，跳过进群验证？`,
    { iconName: "shield-check", confirmText: "确认放行" },
  );
  if (!ok) return;
  await runVerifyAction(item, "verifications/release");
}

async function retryVerification(item) {
  const ok = await confirmAction(
    "重新发起验证",
    `确认给 ${item.member_short} 重新出题？旧的题目和按钮会立即失效，答错次数清零。`,
    { iconName: "refresh-cw", confirmText: "重新出题" },
  );
  if (!ok) return;
  await runVerifyAction(item, "verifications/retry");
}

async function runVerifyAction(item, endpoint) {
  state.busy.add(item.id);
  renderVerifyList();
  try {
    const result = await apiPost(endpoint, { id: item.id });
    toast(result?.message || "操作成功", result?.warning ? "warning" : "success", 4500);
    if (state.tab === "verify") await loadTab("verify");
    await refreshOverviewSilent();
    syncBadges();
  } catch (error) {
    toast(cleanError(error), "error", 5000);
  } finally {
    state.busy.delete(item.id);
    if (state.tab === "verify") renderVerifyList();
  }
}

/* ------------------------------------------------------------------ */
/* 群组                                                               */
/* ------------------------------------------------------------------ */

function renderGroups() {
  const data = state.groups || { items: [], total: 0 };
  const items = data.items || [];
  const page = document.getElementById("page");
  const search = el("input", {
    type: "search",
    placeholder: "搜索群组",
    value: state.filters.groupText,
    oninput: (event) => {
      state.filters.groupText = event.target.value;
      renderGroupList();
    },
  });
  const list = el("div", { class: "group-list", id: "group-list" });
  page.replaceChildren(
    el(
      "div",
      { class: "groups-layout" },
      el(
        "section",
        { class: "card group-list-card" },
        el(
          "div",
          { class: "card-head", style: "padding-bottom:10px" },
          el("div", { class: "card-head-icon" }, icon("users", 16)),
          el(
            "div",
            { class: "card-head-copy" },
            el("h2", { class: "card-title" }, "群组"),
            el("p", { class: "card-subtitle" }, `${items.length} 个已知群`),
          ),
          iconButton("refresh-cw", "刷新", () => refreshCurrent(true), {
            className: "icon-btn",
            size: 14,
          }),
        ),
        el("div", { class: "group-search" }, el("div", { class: "search" }, icon("search", 14), search)),
        list,
      ),
      el("div", { class: "group-detail", id: "group-detail" }),
    ),
    footer(),
  );
  renderGroupList();
  renderGroupDetail();
}

function renderGroupList() {
  const container = document.getElementById("group-list");
  if (!container) return;
  const items = (state.groups?.items || []).filter((item) => {
    const text = state.filters.groupText.trim().toLowerCase();
    if (!text) return true;
    return `${item.label} ${item.umo} ${item.platform_name}`.toLowerCase().includes(text);
  });
  if (!items.length) {
    container.replaceChildren(
      emptyInline("users", "没有群组", "调整搜索条件，或等待插件记录群组。"),
    );
    return;
  }
  container.replaceChildren(
    ...items.map((item) =>
      el(
        "button",
        {
          class: `group-item ${item.umo === state.selectedGroup ? "is-active" : ""}`,
          type: "button",
          title: item.last_seen ? `最近活跃：${formatTime(item.last_seen)}` : item.umo,
          onClick: () => selectGroup(item.umo),
        },
        el(
          "span",
          { class: "group-item-icon" },
          icon(item.profile?.exists ? "shield-check" : "globe", 15),
        ),
        el(
          "span",
          { class: "group-item-copy" },
          el(
            "span",
            { class: "group-item-title" },
            el("span", {}, item.note || item.label),
            item.whitelisted ? null : el("span", { class: "tag is-warning" }, "白名单外"),
          ),
          el("p", { class: "group-item-sub" }, item.umo),
        ),
        el(
          "span",
          { class: "group-item-badges" },
          item.pending_count
            ? el("span", { class: "mini-dot is-hot" }, String(item.pending_count))
            : null,
          item.verification_count
            ? el("span", { class: "mini-dot" }, String(item.verification_count))
            : null,
        ),
      ),
    ),
  );
}

async function selectGroup(umo) {
  if (state.selectedGroup === umo && state.groupDetail?.group?.umo === umo) return;
  state.selectedGroup = umo;
  renderGroupList();
  await loadGroupDetail(umo);
}

async function loadGroupDetail(umo, seq = state.requestSeq) {
  const container = document.getElementById("group-detail");
  if (!container) return;
  container.replaceChildren(
    el("div", { class: "skeleton", style: "height:180px;border-radius:15px" }),
    el("div", { class: "skeleton", style: "height:220px;border-radius:15px" }),
  );
  try {
    const data = await apiGet("groups/detail", { umo });
    if (seq !== state.requestSeq || state.selectedGroup !== umo) return;
    state.groupDetail = data;
    renderGroupDetail();
  } catch (error) {
    if (seq !== state.requestSeq) return;
    container.replaceChildren(
      el(
        "div",
        { class: "card" },
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty-icon" }, icon("alert-triangle", 22)),
          el("h3", {}, "读取群组详情失败"),
          el("p", {}, cleanError(error)),
        ),
      ),
    );
  }
}

function renderGroupDetail() {
  const container = document.getElementById("group-detail");
  if (!container) return;
  const data = state.groupDetail;
  if (!data?.group) {
    container.replaceChildren(
      el(
        "div",
        { class: "card" },
        el(
          "div",
          { class: "empty" },
          el("div", { class: "empty-icon" }, icon("users", 24)),
          el("h3", {}, "选择一个群组"),
          el("p", {}, "左侧列表会展示插件的群配置、待审申请和验证记录。"),
        ),
      ),
    );
    return;
  }
  const group = data.group;
  const features = data.features || [];
  const profile = group.profile || {};
  const header = el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "card-body" },
      el(
        "div",
        { class: "detail-hero" },
        el("div", { class: "detail-avatar" }, icon("shield-check", 25)),
        el(
          "div",
          { class: "detail-copy" },
          el(
            "h2",
            { class: "detail-title" },
            group.note || group.label,
            group.note ? el("span", { class: "tag is-info" }, "已备注") : null,
            profile.exists
              ? el("span", { class: "tag is-success" }, "分群配置")
              : el("span", { class: "tag" }, "继承全局"),
            profile.confirmed
              ? null
              : el(
                  "span",
                  {
                    class: "tag is-warning",
                    title:
                      "旧版迁移时无法确认该 UMO 属于哪个真实群，因此暂不生效。请在群里发送「群管功能」取得真实 group_openid 后修正并确认。",
                  },
                  "未确认 UMO",
                ),
            profile.duplicate
              ? el("span", { class: "tag is-danger" }, "重复 UMO")
              : null,
            group.platform_online
              ? null
              : el("span", { class: "tag is-danger" }, "平台离线"),
            group.whitelisted
              ? null
              : el("span", { class: "tag is-warning" }, "白名单外"),
          ),
          el("p", { class: "detail-umo" }, group.umo),
        ),
        el(
          "div",
          { class: "detail-actions" },
          button(
            "编辑分群配置",
            {
              className: "btn-primary btn-sm",
              onClick: () => openGroupConfig(group),
            },
            icon("settings", 13),
            el("span", {}, profile.exists ? "编辑分群配置" : "创建分群配置"),
          ),
          button(
            group.note ? "编辑备注" : "添加备注",
            {
              className: "btn btn-sm",
              onClick: () => editGroupNote(group),
            },
            icon("pencil", 13),
            el("span", {}, group.note ? "编辑备注" : "添加备注"),
          ),
          profile.exists
            ? button(
                "恢复继承全局",
                {
                  className: "btn-danger btn-sm",
                  onClick: () => restoreGroupInheritance(group),
                },
                icon("refresh-cw", 13),
                el("span", {}, "恢复继承全局"),
              )
            : null,
        ),
      ),
      el(
        "div",
        { class: "detail-stats", style: "margin-top:16px" },
        miniStat("待审申请", group.pending_count),
        miniStat("进群验证", group.verification_count),
        miniStat("插件群管", group.admin_count),
        miniStat("配置来源", profile.exists ? (profile.confirmed ? "本群" : "待确认") : "全局"),
      ),
    ),
  );

  const adminCard = el(
    "section",
    { class: "card" },
    cardHead("shield", "插件群管", "这些 OpenID 拥有本群普通群管权限"),
    el(
      "div",
      { class: "card-body" },
      group.admins?.length
        ? el(
            "div",
            { class: "admin-list" },
            ...group.admins.map((admin) =>
              el(
                "div",
                { class: "admin-row" },
                el("span", { class: "admin-icon" }, icon("user", 13)),
                el("span", { class: "admin-openid", title: admin }, admin),
                iconButton("copy", "复制 OpenID", () => copyText(admin), {
                  className: "btn-ghost btn-icon-only",
                  size: 13,
                }),
                iconButton("user-minus", "移除群管", () => removeAdmin(group, admin), {
                  className: "btn-ghost btn-icon-only",
                  size: 13,
                }),
              ),
            ),
          )
        : el("p", { class: "muted", style: "margin:0;font-size:11.5px" }, "本群还没有插件群管。"),
      adminInput(group),
    ),
  );

  const featureCard = el(
    "section",
    { class: "card" },
    cardHead("sparkles", "本群功能", "已合并分群配置与全局继承"),
    el(
      "div",
      { class: "card-body" },
      features.length
        ? el(
            "div",
            { class: "feature-grid" },
            ...features.map((feature) =>
              el(
                "div",
                { class: "feature-toggle" },
                el("span", {
                  class: `feature-toggle-dot ${feature.enabled ? "is-on" : "is-off"}`,
                }),
                el("span", { style: "flex:1" }, feature.name),
                el("span", { class: "muted", style: "font-size:9px" }, feature.enabled ? "开" : "关"),
              ),
            ),
          )
        : el("p", { class: "muted" }, "暂无功能数据"),
    ),
  );

  const infoCard = el(
    "section",
    { class: "card" },
    cardHead("info", "群组信息", "用于排查平台与配置归属", null),
    el(
      "div",
      { class: "card-body" },
      el(
        "div",
        { class: "kv-list" },
        kvRow(
          "平台",
          group.platform_name === group.platform_id
            ? group.platform_id
            : `${group.platform_name}（${group.platform_id}）`,
        ),
        kvRow("群 OpenID", group.group_openid),
        kvRow("UMO", group.umo),
        kvRow("备注", group.note || "未备注"),
        kvRow("配置来源", (group.sources || []).join(" / ") || "未知"),
        kvRow("最近活跃", group.last_seen ? formatTime(group.last_seen) : "暂无消息记录"),
        kvRow("白名单", group.whitelisted ? "已包含" : "未包含"),
      ),
    ),
  );

  const unconfirmedBanner =
    profile.exists && profile.confirmed === false
      ? el(
          "div",
          { class: "banner" },
          icon("alert-triangle", 15),
          el(
            "div",
            {},
            el("strong", {}, "未确认 UMO 是什么？ "),
            "这是旧版配置迁移时留下的临时标记：当时无法确认这个 UMO 属于哪个真实群，所以该分群配置暂时不生效。请在群里发送「群管功能」取得真实的 group_openid，到原生配置面板修正并勾选确认；或者点「恢复继承全局」删除这条未确认配置。",
          ),
        )
      : null;

  container.replaceChildren(
    ...[
      header,
      unconfirmedBanner,
      el("div", { class: "layout-2", style: "margin-top:0" }, el("div", { class: "stack" }, adminCard, featureCard), el("div", { class: "stack" }, infoCard)),
    ].filter(Boolean),
  );
}

function miniStat(label, value) {
  return el(
    "div",
    { class: "mini-stat" },
    el("p", { class: "mini-stat-label" }, label),
    el("p", { class: "mini-stat-value" }, String(value)),
  );
}

function adminInput(group) {
  const input = el("input", {
    type: "text",
    placeholder: "输入成员 OpenID",
    maxlength: 128,
    "aria-label": "成员 OpenID",
  });
  const addButton = button(
    "添加",
    { className: "btn-primary btn-sm" },
    icon("user-plus", 13),
    el("span", {}, "添加"),
  );
  const add = async () => {
    const value = input.value.trim();
    if (!value) {
      toast("请先输入成员 OpenID", "warning");
      input.focus();
      return;
    }
    try {
      addButton.disabled = true;
      await apiPost("groups/admins", {
        umo: group.umo,
        member_openid: value,
        action: "add",
      });
      input.value = "";
      toast("已添加群管");
      await loadGroupDetail(group.umo);
    } catch (error) {
      toast(cleanError(error), "error");
    } finally {
      addButton.disabled = false;
    }
  };
  addButton.addEventListener("click", add);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      add();
    }
  });
  return el("div", { class: "admin-add" }, input, addButton);
}

async function removeAdmin(group, admin) {
  const ok = await confirmAction(
    "移除插件群管",
    `确认移除 ${admin}？移除后该成员将失去本群插件群管权限。`,
    { iconName: "user-minus", confirmText: "移除", danger: true },
  );
  if (!ok) return;
  try {
    await apiPost("groups/admins", {
      umo: group.umo,
      member_openid: admin,
      action: "remove",
    });
    toast("已移除群管");
    await loadGroupDetail(group.umo);
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

async function restoreGroupInheritance(group) {
  const display = group.note || group.label;
  const ok = await confirmAction(
    "恢复继承全局配置",
    `确认让 ${display} 恢复继承全局配置？这会删除该群的独立配置，群管名单、待审记录和验证记录不会删除。`,
    { iconName: "refresh-cw", confirmText: "恢复继承", danger: true },
  );
  if (!ok) return;
  try {
    await apiPost("config/group/delete", { umo: group.umo });
    toast("已恢复继承全局配置");
    await refreshGroupData(group.umo);
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

async function refreshGroupData(umo) {
  try {
    state.groups = await apiGet("groups");
    if (state.tab === "groups") renderGroupList();
  } catch {
    /* 列表刷新失败时仍然刷新详情 */
  }
  if (state.tab === "groups" && umo) await loadGroupDetail(umo);
}

async function editGroupNote(group) {
  const input = el("input", {
    type: "text",
    value: group.note || "",
    maxlength: 120,
    placeholder: "例如：123456789（QQ群号）或 天文社",
    "aria-label": "群备注",
  });
  const body = el(
    "div",
    {},
    el(
      "p",
      { class: "field-hint", style: "margin:0 0 8px" },
      "备注只用于控制台显示，方便你记住这个 group_openid 对应哪个 QQ 群；不会改变 AstrBot 识别群的方式。",
    ),
    input,
  );
  const saved = await showModal({
    title: group.note ? "编辑群备注" : "添加群备注",
    description: "可以填 QQ 群号、群名或你能认出的任何标记；留空保存即可清除备注。",
    iconName: "pencil",
    confirmText: "保存备注",
    body,
    onConfirm: async () => {
      const result = await apiPost("groups/note", {
        umo: group.umo,
        note: input.value.trim(),
      });
      toast(result?.message || "群备注已保存");
      return true;
    },
  });
  if (saved) await refreshGroupData(group.umo);
}

async function openGroupConfig(group) {
  if (!group.profile?.exists) {
    const ok = await confirmAction(
      "创建分群配置",
      `将为 ${group.note || group.label} 创建独立配置，初始值复制当前全局配置。创建后该群不再跟随全局修改。`,
      { iconName: "settings", confirmText: "创建并编辑" },
    );
    if (!ok) return;
    try {
      await apiPost("config/group/create", { umo: group.umo });
      toast("已创建分群配置");
      await refreshGroupData(group.umo);
    } catch (error) {
      toast(cleanError(error), "error");
      return;
    }
  }
  state.selectedGroup = group.umo;
  state.configScope = "group";
  await navigate("settings");
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(String(value));
    toast("已复制到剪贴板");
  } catch {
    toast("复制失败，请手动选择文本", "warning");
  }
}

/* ------------------------------------------------------------------ */
/* 配置                                                               */
/* ------------------------------------------------------------------ */

function applyConfigData(data) {
  state.config = data;
  state.configScope = data.scope || "global";
  state.formValues = clone(data.values || {});
  state.initialValues = clone(data.values || {});
  renderSettingsSaveState();
}

function settingsDirty() {
  if (!state.config) return false;
  return !deepEqual(state.formValues, state.initialValues);
}

function renderSettings() {
  const data = state.config;
  const page = document.getElementById("page");
  if (!data) return renderLoading();
  const groups = state.groups?.items || [];
  if (state.configScope === "group" && !state.selectedGroup && groups.length) {
    state.selectedGroup = groups[0].umo;
  }

  const scopeSwitch = el(
    "div",
    { class: "segmented", role: "tablist", "aria-label": "配置范围" },
    el(
      "button",
      {
        type: "button",
        class: state.configScope === "global" ? "is-active" : "",
        onclick: () => switchConfigScope("global"),
      },
      "全局配置",
    ),
    el(
      "button",
      {
        type: "button",
        class: state.configScope === "group" ? "is-active" : "",
        onclick: () => switchConfigScope("group"),
      },
      "分群配置",
    ),
  );

  const groupSelect =
    state.configScope === "group"
      ? el(
          "select",
          {
            class: "select",
            onchange: (event) => switchGroup(event.target.value),
          },
          ...(groups.length
            ? groups.map((group) =>
                el(
                  "option",
                  { value: group.umo },
                  group.label + (group.profile?.exists ? " · 已配置" : " · 继承"),
                ),
              )
            : [el("option", { value: "" }, "暂无群组")]),
        )
      : null;
  if (groupSelect) groupSelect.value = state.selectedGroup;

  const warnings = (data.warnings || []).map((warning) =>
    el("div", { class: "banner is-info" }, icon("info", 15), el("span", {}, warning)),
  );

  const sections = (data.sections || []).map((section) => settingsSection(section));

  const saveBar = el(
    "div",
    { class: "save-bar is-hidden", id: "save-bar" },
    el(
      "div",
      { class: "save-state", id: "save-state" },
      icon("info", 14),
      el("span", {}, "所有修改已保存"),
    ),
    button("重置", { className: "btn-ghost btn-sm", onClick: resetSettings }, icon("refresh-cw", 13), el("span", {}, "重置")),
    button("保存更改", { className: "btn-primary btn-sm", id: "save-button", onClick: saveSettings }, icon("check", 14), el("span", {}, "保存更改")),
  );

  const pluginBlocked =
    state.configScope === "group" &&
    data.profile?.exists &&
    data.profile?.confirmed === false;

  if (pluginBlocked) {
    sections.forEach((node) => {
      node.querySelectorAll("input, textarea, select, button").forEach((input) => {
        input.disabled = true;
      });
    });
  }

  page.replaceChildren(
    ...[
      el(
        "div",
        { class: "scope-bar" },
        scopeSwitch,
        groupSelect,
        state.configScope === "group" && data.profile?.exists
          ? button(
              "恢复继承全局",
              {
                className: "btn-danger btn-sm",
                onClick: async () => {
                  const group = {
                    umo: state.selectedGroup,
                    label: state.selectedGroup,
                    note: "",
                  };
                  await restoreGroupInheritance(group);
                  await reloadConfig();
                },
              },
              icon("refresh-cw", 13),
              el("span", {}, "恢复继承全局"),
            )
          : null,
        el(
          "span",
          { class: "muted", style: "margin-left:auto;font-size:10.5px" },
          state.configScope === "group"
            ? "仅影响当前选中的群"
            : "作为所有未单独配置群组的默认值",
        ),
      ),
      warnings.length ? el("div", { class: "banner-list" }, ...warnings) : null,
      el("div", { class: "settings-layout", id: "settings-layout" }, ...sections),
      saveBar,
      footer(),
    ].filter(Boolean),
  );
  renderSettingsSaveState();
  applyFieldConditions();
}

function settingsSection(section) {
  const fields = (section.fields || []).map((field) => settingsField(field));
  const details = el(
    "details",
    { class: "card settings-section", open: true, dataset: { section: section.key } },
    el(
      "summary",
      {},
      el("span", { class: "settings-section-icon" }, icon(section.icon || "settings", 15)),
      el(
        "span",
        { style: "min-width:0;flex:1" },
        el("span", { class: "settings-section-title" }, section.title),
        section.hint ? el("p", { class: "settings-section-hint" }, section.hint) : null,
      ),
      el("span", { class: "settings-section-chevron" }, icon("chevron-right", 15)),
    ),
    el("div", { class: "settings-fields" }, ...fields),
  );
  return details;
}

function settingsField(field) {
  const key = field.key;
  const value = state.formValues[key];
  const control = fieldControl(field, value);
  const node = el(
    "div",
    {
      class: "field",
      dataset: {
        key,
        condition: field.condition ? JSON.stringify(field.condition) : "",
      },
    },
    el(
      "div",
      {},
      el("p", { class: "field-label" }, field.label),
      field.hint ? el("p", { class: "field-hint" }, field.hint) : null,
    ),
    el("div", { class: "field-control" }, control),
  );
  return node;
}

function fieldControl(field, value) {
  const key = field.key;
  if (field.kind === "bool") {
    const statusLabel = el("p", { class: "field-label" }, value ? "已开启" : "已关闭");
    const toggle = el("button", {
      class: "switch",
      type: "button",
      role: "switch",
      "aria-checked": value ? "true" : "false",
      "aria-label": field.label,
      onclick: () => {
        state.formValues[key] = !state.formValues[key];
        const checked = Boolean(state.formValues[key]);
        toggle.setAttribute("aria-checked", checked ? "true" : "false");
        statusLabel.textContent = checked ? "已开启" : "已关闭";
        markSettingsDirty();
        applyFieldConditions();
      },
    });
    return el(
      "div",
      { class: "switch-row" },
      toggle,
      el(
        "div",
        { class: "switch-row-copy" },
        statusLabel,
        el("p", { class: "field-hint" }, "点击切换"),
      ),
    );
  }

  if (field.kind === "int") {
    const input = el("input", {
      type: "number",
      value: value ?? "",
      min: field.min,
      max: field.max,
      step: field.step || 1,
      oninput: (event) => {
        state.formValues[key] = event.target.value === "" ? "" : Number(event.target.value);
        markSettingsDirty();
      },
    });
    return el(
      "div",
      { class: "field-inline" },
      input,
      field.unit ? el("span", { class: "field-unit" }, field.unit) : null,
    );
  }

  if (field.kind === "text") {
    const textarea = el("textarea", {
      rows: field.rows || 4,
      placeholder: field.placeholder || "",
      oninput: (event) => {
        state.formValues[key] = event.target.value;
        markSettingsDirty();
      },
    });
    textarea.value = value ?? "";
    return textarea;
  }

  if (field.kind === "string") {
    if (field.options?.length) {
      const select = el(
        "select",
        {
          onchange: (event) => {
            state.formValues[key] = event.target.value;
            markSettingsDirty();
            applyFieldConditions();
          },
        },
        ...field.options.map((option) => el("option", { value: option }, option)),
      );
      select.value = value ?? field.options[0];
      return select;
    }
    const input = el("input", {
      type: "text",
      value: value ?? "",
      placeholder: field.placeholder || "",
      maxlength: 512,
      oninput: (event) => {
        state.formValues[key] = event.target.value;
        markSettingsDirty();
      },
    });
    return el(
      "div",
      { class: "field-inline" },
      input,
      field.unit ? el("span", { class: "field-unit" }, field.unit) : null,
    );
  }

  if (field.kind === "list") {
    if (field.choices?.length) {
      const selected = new Set(Array.isArray(value) ? value : []);
      return el(
        "div",
        { class: "checkbox-grid" },
        ...field.choices.map((choice) => {
          const input = el("input", {
            type: "checkbox",
            checked: selected.has(choice),
            onchange: (event) => {
              if (event.target.checked) selected.add(choice);
              else selected.delete(choice);
              state.formValues[key] = field.choices.filter((item) => selected.has(item));
              event.target.closest(".check-chip")?.classList.toggle("is-checked", event.target.checked);
              markSettingsDirty();
            },
          });
          return el(
            "label",
            { class: `check-chip ${selected.has(choice) ? "is-checked" : ""}` },
            input,
            choice,
          );
        }),
      );
    }
    if (key === "custom_questions") {
      const textarea = el("textarea", {
        rows: field.rows || 5,
        placeholder: field.placeholder || "",
        oninput: (event) => {
          state.formValues[key] = event.target.value
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean);
          markSettingsDirty();
        },
      });
      textarea.value = Array.isArray(value) ? value.join("\n") : value ?? "";
      return textarea;
    }
    return tagEditor(field, Array.isArray(value) ? value : []);
  }

  return el("input", { type: "text", value: value ?? "" });
}

function tagEditor(field, values) {
  const key = field.key;
  const tags = el("div", { style: "display:contents" });
  const input = el("input", {
    class: "tag-input",
    type: "text",
    placeholder: field.placeholder || "输入后按回车添加",
    "aria-label": field.label,
  });
  const wrapper = el("div", { class: "tag-editor" }, tags, input);

  function renderTags() {
    tags.replaceChildren(
      ...values.map((value, index) =>
        el(
          "span",
          { class: "tag-item" },
          el("span", { title: value }, value),
          el(
            "button",
            {
              class: "tag-remove",
              type: "button",
              "aria-label": `移除 ${value}`,
              onclick: () => {
                values.splice(index, 1);
                state.formValues[key] = [...values];
                renderTags();
                markSettingsDirty();
              },
            },
            icon("x", 10),
          ),
        ),
      ),
    );
  }

  function addValue() {
    const raw = input.value.trim();
    if (!raw) return;
    const items = raw
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    let changed = false;
    for (const item of items) {
      if (!values.includes(item)) {
        values.push(item);
        changed = true;
      }
    }
    input.value = "";
    if (changed) {
      state.formValues[key] = [...values];
      renderTags();
      markSettingsDirty();
    }
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addValue();
    }
    if (event.key === "Backspace" && !input.value && values.length) {
      values.pop();
      state.formValues[key] = [...values];
      renderTags();
      markSettingsDirty();
    }
  });
  input.addEventListener("blur", addValue);
  wrapper.addEventListener("click", () => input.focus());
  renderTags();
  return wrapper;
}

function applyFieldConditions() {
  const fields = document.querySelectorAll("#settings-layout .field[data-condition]");
  fields.forEach((field) => {
    let condition = null;
    try {
      condition = JSON.parse(field.dataset.condition || "null");
    } catch {
      condition = null;
    }
    if (!condition || typeof condition !== "object") return;
    const visible = Object.entries(condition).every(
      ([key, expected]) => state.formValues[key] === expected,
    );
    field.classList.toggle("is-hidden", !visible);
  });
  document.querySelectorAll("#settings-layout .settings-section").forEach((section) => {
    const fieldsInSection = section.querySelectorAll(".field");
    const anyVisible = Array.from(fieldsInSection).some(
      (field) => !field.classList.contains("is-hidden"),
    );
    section.classList.toggle("hidden", fieldsInSection.length > 0 && !anyVisible);
  });
}

function markSettingsDirty() {
  renderSettingsSaveState();
}

function renderSettingsSaveState() {
  const bar = document.getElementById("save-bar");
  if (!bar) return;
  const dirty = settingsDirty();
  const changes = countChanges();
  bar.classList.toggle("is-hidden", !dirty);
  const stateNode = document.getElementById("save-state");
  if (stateNode) {
    stateNode.classList.toggle("is-dirty", dirty);
    stateNode.replaceChildren(
      icon(dirty ? "alert-triangle" : "check-circle", 14),
      el("span", {}, dirty ? `${changes} 项已修改` : "所有修改已保存"),
    );
  }
  const save = document.getElementById("save-button");
  if (save) save.disabled = !dirty;
}

function countChanges() {
  let count = 0;
  for (const key of Object.keys(state.formValues)) {
    if (!deepEqual(state.formValues[key], state.initialValues[key])) count += 1;
  }
  return count;
}

async function switchConfigScope(scope) {
  if (scope === state.configScope) return;
  if (settingsDirty()) {
    const ok = await confirmAction(
      "切换配置范围",
      "当前修改尚未保存，切换后将丢失，确定继续？",
      { confirmText: "继续切换", danger: true },
    );
    if (!ok) return;
  }
  if (scope === "group" && !(state.groups?.items || []).length) {
    toast("暂无可配置的群组", "warning");
    return;
  }
  state.configScope = scope;
  if (scope === "group" && !state.selectedGroup) {
    state.selectedGroup = state.groups?.items?.[0]?.umo || "";
  }
  await reloadConfig();
}

async function switchGroup(umo) {
  if (umo === state.selectedGroup) return;
  if (settingsDirty()) {
    const ok = await confirmAction(
      "切换群组",
      "当前修改尚未保存，切换后将丢失，确定继续？",
      { confirmText: "继续切换", danger: true },
    );
    if (!ok) return;
  }
  state.selectedGroup = umo;
  await reloadConfig();
}

async function reloadConfig() {
  try {
    const umo = state.configScope === "group" ? state.selectedGroup : "";
    const data = await apiGet("config", umo ? { umo } : undefined);
    applyConfigData(data);
    renderSettings();
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

async function saveSettings() {
  if (!settingsDirty()) return;
  if (state.configScope === "group" && !state.selectedGroup) {
    toast("请先选择一个群组", "warning");
    return;
  }
  const values = {};
  for (const key of Object.keys(state.formValues)) {
    if (!deepEqual(state.formValues[key], state.initialValues[key])) {
      values[key] = state.formValues[key];
    }
  }
  const saveButton = document.getElementById("save-button");
  if (saveButton) {
    saveButton.disabled = true;
    saveButton.replaceChildren(el("span", { class: "spinner" }), el("span", {}, "保存中…"));
  }
  try {
    const result = await apiPost("config/save", {
      scope: state.configScope,
      umo: state.configScope === "group" ? state.selectedGroup : "",
      values,
    });
    toast(result?.message || "配置已保存");
    if (result?.config) applyConfigData(result.config);
    else await reloadConfig();
    renderSettings();
    if (state.overview) {
      try {
        state.overview = await apiGet("overview");
        syncBadges();
      } catch {
        /* 忽略后台刷新失败 */
      }
    }
  } catch (error) {
    toast(cleanError(error), "error", 5000);
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.replaceChildren(icon("check", 14), el("span", {}, "保存更改"));
    }
    renderSettingsSaveState();
  }
}

async function resetSettings() {
  if (!settingsDirty()) return;
  const ok = await confirmAction(
    "撤销未保存的修改",
    "所有尚未保存的修改都会恢复为上次保存的值。",
    { confirmText: "撤销修改", danger: true },
  );
  if (!ok) return;
  state.formValues = clone(state.initialValues);
  renderSettings();
}

/* ------------------------------------------------------------------ */
/* 数据                                                               */
/* ------------------------------------------------------------------ */

function renderData() {
  const page = document.getElementById("page");
  const runtime = state.overview?.runtime || {};
  const plugin = state.overview?.plugin || {};
  const context = state.context || {};
  page.replaceChildren(
    el(
      "div",
      { class: "data-grid" },
      dataCard(
      "database",
      "运行数据快照",
      "导出 state.json，包含待审映射、审批完成标记、群管名单与验证记录。文件可能包含成员 OpenID，请妥善保管。",
      "导出 state.json",
      () => downloadState(),
    ),
    dataCard(
      "file-json",
      "插件配置快照",
      "以 JSON 形式导出当前完整配置，便于迁移、备份或排查配置问题。此操作不会修改运行中的配置。",
      "导出配置 JSON",
      () => downloadConfig(),
    ),
    dataCard(
      "upload",
      "安全导入运行数据",
      "导入 state.json 前会先校验结构、显示影响范围，并自动备份当前运行数据；可选择合并或覆盖。",
      "选择 state.json",
      () => pickStateImport(),
      "upload",
    ),
    dataCard(
      "upload",
      "安全导入配置快照",
      "导入插件配置前会校验布局版本和分群 UMO，并自动备份当前配置；不会接受不匹配的快照。",
      "选择配置 JSON",
      () => pickConfigImport(),
      "upload",
    ),
    el(
      "section",
      { class: "data-card" },
      el("div", { class: "data-card-icon" }, icon("gauge", 19)),
      el("h3", {}, "视图信息"),
      el(
        "div",
        { class: "kv-list", style: "width:100%" },
        kvRow("插件版本", `v${plugin.version || PLUGIN_VERSION}`),
        kvRow("视图名称", context.pageName || "console"),
        kvRow("WebUI 语言", context.locale || "zh-CN"),
        kvRow("主题", context.isDark ? "暗色" : "亮色"),
        kvRow(
          "主题色",
          state.themeColor ? state.themeColor.toUpperCase() : "跟随 AstrBot",
        ),
        kvRow("待审 / 验证", `${runtime.pending_count || 0} / ${runtime.verification_count || 0}`),
        kvRow("已接入群", String(runtime.group_count || 0)),
      ),
    ),
    el(
      "section",
      { class: "data-card" },
      el("div", { class: "data-card-icon" }, icon("shield-check", 19)),
      el("h3", {}, "安全边界"),
      el(
        "p",
        {},
        "本视图运行在 AstrBot Dashboard 的受限 iframe 中，不能读取 Dashboard Cookie 或 LocalStorage；所有操作都通过 bridge 转发到插件后端，并由 Dashboard 会话鉴权。",
      ),
      el(
        "p",
        {},
        "建议只在受信任的网络环境开放 Dashboard，并定期备份 data/plugin_data/astrbot_plugin_qq_group_manage/state.json。",
      ),
      button(
        "打开视图配置",
        {
          className: "btn",
          onClick: () => navigate("settings"),
        },
        icon("settings", 14),
        el("span", {}, "打开视图配置"),
      ),
    ),
    ),
    footer(),
  );
}

function dataCard(iconName, title, description, actionLabel, action, actionIcon = "download") {
  return el(
    "section",
    { class: "data-card" },
    el("div", { class: "data-card-icon" }, icon(iconName, 19)),
    el("h3", {}, title),
    el("p", {}, description),
    button(actionLabel, { className: "btn", onClick: action }, icon(actionIcon, 14), el("span", {}, actionLabel)),
  );
}

async function downloadState() {
  try {
    if (bridge?.download) {
      const result = await bridge.download("export/state", {}, "qq-group-manage-state.json");
      toast(`已开始下载${result?.filename ? `：${result.filename}` : ""}`);
      return;
    }
    toast("当前 bridge 不支持文件下载", "warning");
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

async function downloadConfig() {
  try {
    const data = await apiGet("export/config");
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `qq-group-manage-config-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    toast("配置已导出");
  } catch (error) {
    toast(cleanError(error), "error");
  }
}

function pickStateImport() {
  pickImportFile("state");
}

function pickConfigImport() {
  pickImportFile("config");
}

function pickImportFile(kind) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.style.display = "none";
  input.addEventListener("change", async () => {
    const file = input.files?.[0];
    input.remove();
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const preview = await apiPost("import/preview", { kind, data });
      openImportConfirm(kind, data, preview?.preview || {});
    } catch (error) {
      toast(cleanError(error), "error");
    }
  });
  document.body.appendChild(input);
  input.click();
}

function importSummary(kind, preview) {
  if (kind === "state") {
    return [
      `群管名单：${preview.admin_groups || 0} 个群 / ${preview.admin_members || 0} 人`,
      `待审申请：${preview.pending || 0} 条`,
      `进群验证：${preview.verifications || 0} 条`,
      `已记录群组：${preview.seen_groups || 0} 个`,
      `群备注：${preview.group_notes || 0} 条`,
      `界面偏好：${preview.ui_preferences || 0} 项`,
    ];
  }
  return [
    `快照版本：${preview.version || "未标注"}`,
    `分群配置：${preview.groups || 0} 个`,
    `全局配置段：${preview.global_settings || 0} 项`,
    `作用域配置：${preview.scope_keys || 0} 项`,
    `导出时间：${preview.exported_at || "未标注"}`,
  ];
}

async function openImportConfirm(kind, data, preview) {
  const modeName = `import-mode-${Date.now()}`;
  const merge = el("input", {
    type: "radio",
    name: modeName,
    value: "merge",
    checked: true,
  });
  const replace = el("input", {
    type: "radio",
    name: modeName,
    value: "replace",
  });
  const body = el(
    "div",
    {},
    el(
      "div",
      { class: "banner is-warning", style: "margin:0 0 12px" },
      icon("alert-triangle", 15),
      el(
        "div",
        {},
        "导入前会自动备份当前数据。覆盖模式会用快照替换对应的现有记录，请确认这是你要的效果。",
      ),
    ),
    el("div", { class: "kv-list", style: "margin-bottom:12px" }, ...importSummary(kind, preview).map((line) => kvRow(line.split("：")[0], line.split("：").slice(1).join("：")))),
    el("label", { class: "field", style: "display:flex;gap:8px;align-items:flex-start;margin-bottom:8px" }, merge, el("span", {}, "合并：保留当前记录，快照补充/更新同名项")),
    el("label", { class: "field", style: "display:flex;gap:8px;align-items:flex-start" }, replace, el("span", {}, "覆盖：用快照替换现有运行数据/分群配置")),
  );
  const result = await showModal({
    title: kind === "state" ? "导入运行数据" : "导入插件配置",
    description: "请选择导入模式；完成后视图会自动刷新。",
    iconName: "upload",
    confirmText: "确认导入",
    body,
    onConfirm: async () => {
      const selected = body.querySelector(`input[name="${modeName}"]:checked`);
      const mode = selected?.value === "replace" ? "replace" : "merge";
      const endpoint = kind === "state" ? "import/state" : "import/config";
      const res = await apiPost(endpoint, { data, mode });
      toast(
        `导入完成${res?.backup ? `，已备份到 ${res.backup}` : ""}`,
        "success",
      );
      window.setTimeout(() => window.location.reload(), 800);
      return true;
    },
  });
  return result;
}

/* ------------------------------------------------------------------ */
/* 工具：分组、时间、空状态                                           */
/* ------------------------------------------------------------------ */

function uniqueGroups(items) {
  const map = new Map();
  for (const item of items) {
    if (!item.group_umo) continue;
    if (!map.has(item.group_umo)) map.set(item.group_umo, item.group_label || item.group_umo);
  }
  return Array.from(map.entries());
}

/* 启动 */
boot().catch((error) => {
  renderFatal("群管控制台启动失败", cleanError(error));
});
