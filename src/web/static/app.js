// Ask the Graph: asks /api/ask, shows the answer with its citations, the case board and the evidence.

const EXAMPLES = [
  "Is Captain Carter the same character as Peggy Carter?",
  "Who killed He Who Remains?",
  "Who has been a member of both the Avengers and the Guardians of the Galaxy?",
  "Who directed the most films?",
];
const STRATEGIES = {
  local: "Local: the details around the titles, characters, people and teams the question names. The default.",
  global: "Global: the summaries of phases, sagas, series and teams, for big-picture questions.",
  drift: "DRIFT: starts from a broad summary and steps down to the closest titles' plot details.",
};
const CARD_W = 190;

const $ = (id) => document.getElementById(id);
let strategy = "local";
let cy = null;

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// --- left: examples, strategy, answer ------------------------------------------------------

function renderExamples() {
  $("examples").replaceChildren(...EXAMPLES.map((q) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = q;
    b.addEventListener("click", () => { $("question").value = q; ask(q); });
    return b;
  }));
}

function renderStrategies() {
  $("strategies").replaceChildren(...Object.keys(STRATEGIES).map((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(name === strategy));
    b.textContent = name === "drift" ? "DRIFT" : name[0].toUpperCase() + name.slice(1);
    b.addEventListener("click", () => { strategy = name; renderStrategies(); });
    return b;
  }));
  $("strategy-help").textContent = STRATEGIES[strategy];
}

// citations as the answer step reads them (src/retrieval/answer.py): [12], [12, 40], [12-15]
const CITATION = /\[(\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*)\]/g;

function numbers(group) {
  return group.split(",").flatMap((part) => {
    const [a, b] = part.split(/[-–]/).map((x) => parseInt(x, 10));
    return b ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : [a];
  });
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(CITATION, (_, group) => `<button type="button" class="cite" data-ns="${numbers(group).join(" ")}">`
      + `${group.replace(/\s+/g, "").replace(/-/g, "–").replace(/,/g, ", ")}</button>`);
}

function renderAnswer(text) {
  const html = text.split(/\n{2,}/).map((para) => {
    const lines = para.split("\n");
    if (lines.every((l) => /^\s*[-*] /.test(l))) {
      return "<ul>" + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`).join("") + "</ul>";
    }
    return `<p>${lines.map(inline).join("<br>")}</p>`;
  }).join("");
  $("answer").innerHTML = html;
  $("answer").querySelectorAll(".cite").forEach((b) => b.addEventListener("click", () => highlight(b)));
}

function renderSteps(data) {
  const rows = [
    ["Strategy", data.strategy === "drift" ? "DRIFT" : data.strategy],
    ["Named", data.named.length ? data.named.join(", ") : "nothing the name index knows"],
    ["Views", data.views.length ? data.views.join(", ") : "none called"],
    ["Cited", `${data.cited.length} lines`],
    ["Time", `retrieval ${data.retrieval_seconds.toFixed(2)} s, answer ${data.answer_seconds.toFixed(1)} s`],
  ];
  $("steps-list").replaceChildren(...rows.flatMap(([k, v]) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    return [dt, dd];
  }));
  $("steps").hidden = false;
}

// --- right: evidence -------------------------------------------------------------------------

function renderCited(lines) {
  $("cited-label").textContent = lines.length ? `${lines.length} lines cited in the answer` : "";
  $("cited").replaceChildren(...lines.map((line) => {
    const li = document.createElement("li");
    li.dataset.n = line.n;
    li.innerHTML = `<span class="num"><span class="cite">${line.n}</span></span>
      <span class="block">${escapeHtml(blockName(line.block))}</span>
      <span class="text">${escapeHtml(line.text.replace(/^- /, ""))}</span>`;
    return li;
  }));
}

// a citation badge: light it and the lines it cites, and bring the first into view
function highlight(badge) {
  document.querySelectorAll(".cite.on, .cited li.on").forEach((e) => e.classList.remove("on"));
  badge.classList.add("on");
  const items = badge.dataset.ns.split(" ").map((n) => $("cited").querySelector(`li[data-n="${n}"]`)).filter(Boolean);
  items.forEach((item) => item.classList.add("on"));
  if (items.length) items[0].scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// a block heading without its aliases, short enough for the evidence list
function blockName(block) {
  const name = (block || "context").split(". Also known as")[0];
  return name.length > 80 ? name.slice(0, 77) + "…" : name;
}

function showSelected(html) { $("selected").innerHTML = html; }

function list(items) { return "<ul>" + items.map((i) => `<li>${escapeHtml(i)}</li>`).join("") + "</ul>"; }

// --- middle: the board ------------------------------------------------------------------------

function cardHeight(card) {
  const nameLines = Math.ceil(card.label.length / 20);
  return 46 + 20 * nameLines + (card.under ? 18 : 0);
}

function renderBoard(board) {
  $("cards").replaceChildren();
  if (cy) cy.destroy();
  $("board-empty").hidden = board.cards.length > 0;
  if (!board.cards.length) { cy = null; return; }

  const byId = Object.fromEntries(board.cards.map((c) => [c.id, c]));
  cy = cytoscape({
    container: $("board"),
    elements: [
      ...board.cards.map((c) => ({ data: { id: c.id, w: CARD_W, h: cardHeight(c) } })),
      ...board.links.map((l) => ({ data: { id: l.id, source: l.source, target: l.target, label: l.label },
                                   classes: l.plot ? "plot" : "data" })),
    ],
    style: [
      { selector: "node", style: { shape: "round-rectangle", width: "data(w)", height: "data(h)",
                                   "background-opacity": 0, "border-width": 0, label: "" } },
      { selector: "edge", style: {
          width: 1.6, "curve-style": "bezier", "target-arrow-shape": "triangle", "arrow-scale": 0.9,
          "line-color": "#9a9ea3", "target-arrow-color": "#9a9ea3", label: "data(label)", "font-size": 12,
          "font-family": "Inter, system-ui, sans-serif", color: "#3a3a3a", "text-background-color": "#ffffff",
          "text-background-opacity": 1, "text-background-shape": "roundrectangle", "text-background-padding": 4,
          "text-border-color": "#e4e3df", "text-border-width": 1, "text-border-opacity": 1 } },
      { selector: "edge.plot", style: { "line-color": "#e0624f", "target-arrow-color": "#e0624f", color: "#c0473a" } },
      { selector: "edge:selected", style: { width: 3 } },
    ],
    layout: { name: "cose", animate: false, nodeDimensionsIncludeLabels: false, idealEdgeLength: 150,
              nodeRepulsion: 900000, padding: 70, randomize: true, componentSpacing: 120 },
    maxZoom: 1.2,
    minZoom: 0.2,
  });

  const layer = $("cards");
  const elements = {};
  board.cards.forEach((c) => {
    const div = document.createElement("div");
    div.className = `card ${c.kind}`;
    div.innerHTML = `<div class="kind">${escapeHtml(c.kind)}</div><div class="name">${escapeHtml(c.label)}</div>`
      + (c.under ? `<div class="under">${escapeHtml(c.under)}</div>` : "");
    layer.appendChild(div);
    elements[c.id] = div;
  });

  const place = () => {
    const z = cy.zoom();
    cy.nodes().forEach((n) => {
      const p = n.renderedPosition();
      const div = elements[n.id()];
      div.style.transform = `translate(${p.x - (CARD_W * z) / 2}px, ${p.y - (n.data("h") * z) / 2}px) scale(${z})`;
    });
  };
  cy.on("render", place);
  place();

  cy.on("tap", "node", (e) => {
    const c = byId[e.target.id()];
    Object.values(elements).forEach((d) => d.classList.remove("selected"));
    elements[c.id].classList.add("selected");
    const touching = board.links.filter((l) => l.source === c.id || l.target === c.id).map((l) => {
      const other = byId[l.source === c.id ? l.target : l.source];
      return `${l.source === c.id ? "" : "← "}${l.label} ${other.label}: ${l.evidence[0]}`;
    });
    showSelected(`<div class="kindtag">${escapeHtml(c.kind)}</div><h3>${escapeHtml(c.label)}</h3>`
      + (c.under ? escapeHtml(c.under) : "") + (touching.length ? list(touching) : "<p>No links to the other cards.</p>"));
  });
  cy.on("tap", "edge", (e) => {
    const l = board.links.find((x) => x.id === e.target.id());
    showSelected(`<div class="kindtag">${l.plot ? "plot summary" : "data source"}</div>`
      + `<h3>${escapeHtml(byId[l.source].label)} ${escapeHtml(l.label)} ${escapeHtml(byId[l.target].label)}</h3>`
      + list(l.evidence));
  });
  cy.on("tap", (e) => {
    if (e.target === cy) {
      Object.values(elements).forEach((d) => d.classList.remove("selected"));
      showSelected("Select a card or a link on the board to read its evidence.");
    }
  });
}

// --- asking -----------------------------------------------------------------------------------

async function ask(question) {
  document.querySelectorAll(".examples button").forEach((b) => b.classList.toggle("active", b.textContent === question));
  $("thread").hidden = false;
  $("asked").textContent = question;
  $("status").textContent = "Searching the graph and writing the answer…";
  $("status").className = "status";
  $("steps").hidden = true;
  $("answer").replaceChildren();
  $("ask").disabled = true;
  try {
    const response = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, strategy }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    $("status").textContent = "Done";
    renderSteps(data);
    renderAnswer(data.answer);
    renderCited(data.cited);
    renderBoard(data.board);
    showSelected("Select a card or a link on the board to read its evidence.");
  } catch (error) {
    $("status").textContent = error.message;
    $("status").className = "status error";
  } finally {
    $("ask").disabled = false;
  }
}

$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("question").value.trim();
  if (q) ask(q);
});
$("fit").addEventListener("click", () => { if (cy) cy.fit(undefined, 70); });
renderExamples();
renderStrategies();
