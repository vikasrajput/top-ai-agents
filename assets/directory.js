(() => {
  "use strict";
  const form = document.querySelector("[data-filters]");
  if (!form) return;
  const search = form.querySelector('[name="search"]');
  const category = form.querySelector('[name="category"]');
  const kind = form.querySelector('[name="kind"]');
  const sort = form.querySelector('[name="sort"]');
  const status = document.querySelector("[data-results]");
  const tables = [...document.querySelectorAll("table[data-directory]")];
  const rowsByTable = new Map(tables.map(table => [
    table, [...table.tBodies[0].rows]
  ]));
  const numeric = (row, field) => {
    const value = row.dataset[field];
    return value === "" || value === undefined ? null : Number(value);
  };
  function update() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const table of tables) {
      const rows = rowsByTable.get(table);
      rows.sort((a, b) => {
        const nameOrder = a.dataset.name.localeCompare(b.dataset.name);
        if (sort.value === "name") return nameOrder;
        if (sort.value === "category") {
          return a.dataset.category.localeCompare(b.dataset.category) || nameOrder;
        }
        const field = sort.value === "period" ? "period" : "stars";
        const left = numeric(a, field);
        const right = numeric(b, field);
        if (left === null && right === null) return nameOrder;
        if (left === null) return 1;
        if (right === null) return -1;
        return right - left || nameOrder;
      });
      let count = 0;
      for (const row of rows) {
        const matches = (!query || row.textContent.toLocaleLowerCase().includes(query))
          && (!category.value || row.dataset.category === category.value)
          && (!kind.value || row.dataset.kind === kind.value);
        row.hidden = !matches;
        if (matches) count++;
        table.tBodies[0].append(row);
      }
      visible += count;
      const empty = table.closest("[data-table-section]").querySelector("[data-empty]");
      if (empty) {
        empty.hidden = count !== 0;
        if (rows.length && count === 0) {
          empty.textContent = "No entries match the current filters.";
        }
      }
    }
    status.textContent = `${visible} matching entries across the directory tables.`;
  }
  form.hidden = false;
  form.addEventListener("submit", event => event.preventDefault());
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  status.textContent = `${[...rowsByTable.values()].reduce((sum, rows) => sum + rows.length, 0)} entries. Use search or filters to narrow the directory.`;
})();
