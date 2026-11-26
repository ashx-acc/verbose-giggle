(() => {
  "use strict";

  const API_BASE = "/api/community";

  const state = {
    rows: [],
    editingCode: null,
    search: "",
  };

  const els = {
    tbody: document.getElementById("communityTableBody"),
    visibleCount: document.getElementById("visibleCount"),
    communityCount: document.getElementById("communityCount"),
    search: document.getElementById("communitySearch"),
    addButton: document.getElementById("addCommunityButton"),
    dialog: document.getElementById("communityDialog"),
    form: document.getElementById("communityForm"),
    formError: document.getElementById("formError"),
    dialogEyebrow: document.getElementById("dialogEyebrow"),
    dialogTitle: document.getElementById("dialogTitle"),
    saveButton: document.getElementById("saveCommunityButton"),
    closeButton: document.getElementById("closeDialogButton"),
    cancelButton: document.getElementById("cancelDialogButton"),
    toast: document.getElementById("toast"),
    code: document.getElementById("community_code"),
    name: document.getElementById("community_name"),
    population: document.getElementById("population"),
    areaSqmile: document.getElementById("area_sqmile"),
    areaSqkm: document.getElementById("area_sqkm"),
    densitySqmi: document.getElementById("density_per_sqmi"),
    densitySqkm: document.getElementById("density_per_sqkm"),
  };

  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => {
      const entities = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return entities[character];
    });

  const formatNumber = (value) => {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (Number.isNaN(number)) return "—";
    return number.toLocaleString(undefined, {
      maximumFractionDigits: 2,
    });
  };

  let toastTimer = null;

  function showToast(message, isError = false) {
    els.toast.textContent = message;
    els.toast.classList.toggle("error", isError);
    els.toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      els.toast.classList.remove("visible");
    }, 3600);
  }

  function setFormError(message) {
    if (!message) {
      els.formError.hidden = true;
      els.formError.textContent = "";
      return;
    }
    els.formError.hidden = false;
    els.formError.textContent = message;
  }

  async function readError(response) {
    try {
      const payload = await response.json();
      if (Array.isArray(payload.detail)) {
        return payload.detail
          .map((item) => {
            const location = Array.isArray(item.loc)
              ? item.loc.slice(1).join(".")
              : "";
            return location ? `${location}: ${item.msg}` : item.msg;
          })
          .join("; ");
      }
      if (typeof payload.detail === "string") return payload.detail;
      return JSON.stringify(payload);
    } catch {
      return response.statusText || `Request failed (${response.status})`;
    }
  }

  function numberOrNull(value) {
    const text = String(value ?? "").trim();
    if (text === "") return null;
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  }

  function renderRows(rows) {
    els.visibleCount.textContent = `${rows.length} shown`;
    if (!state.search) {
      els.communityCount.textContent = rows.length.toLocaleString();
    }

    if (!rows.length) {
      els.tbody.innerHTML = `
        <tr>
          <td colspan="8" class="empty-state">No community rows match this search.</td>
        </tr>`;
      return;
    }

    els.tbody.innerHTML = rows
      .map(
        (row) => `
        <tr>
          <td><span class="code-pill">${escapeHtml(row.community_code)}</span></td>
          <td><strong>${escapeHtml(row.community_name)}</strong></td>
          <td class="num">${formatNumber(row.population)}</td>
          <td class="num">${formatNumber(row.area_sqmile)}</td>
          <td class="num">${formatNumber(row.area_sqkm)}</td>
          <td class="num">${formatNumber(row.density_per_sqmi)}</td>
          <td class="num">${formatNumber(row.density_per_sqkm)}</td>
          <td class="actions-col">
            <button class="btn btn-tiny btn-ghost" type="button"
              data-action="edit" data-code="${escapeHtml(row.community_code)}">Edit</button>
            <button class="btn btn-tiny btn-ghost" type="button"
              data-action="patch" data-code="${escapeHtml(row.community_code)}"
              data-name="${escapeHtml(row.community_name)}">Patch</button>
            <button class="btn btn-tiny btn-danger" type="button"
              data-action="delete" data-code="${escapeHtml(row.community_code)}"
              data-name="${escapeHtml(row.community_name)}">Delete</button>
          </td>
        </tr>`
      )
      .join("");
  }

  async function loadCommunities() {
    const url = state.search
      ? `${API_BASE}?search=${encodeURIComponent(state.search)}`
      : API_BASE;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    state.rows = await response.json();
    renderRows(state.rows);
  }

  function setFieldValue(field, value) {
    field.value = value === null || value === undefined ? "" : value;
  }

  function openCreateDialog() {
    state.editingCode = null;
    els.form.reset();
    setFormError("");
    els.code.disabled = false;
    els.dialogEyebrow.textContent = "Create";
    els.dialogTitle.textContent = "Add community area";
    els.saveButton.textContent = "Create community";
    els.dialog.showModal();
    els.code.focus();
  }

  function openEditDialog(communityCode) {
    const row = state.rows.find(
      (item) => Number(item.community_code) === Number(communityCode)
    );
    if (!row) {
      showToast("That community row is no longer loaded.", true);
      return;
    }

    state.editingCode = Number(communityCode);
    setFormError("");
    setFieldValue(els.code, row.community_code);
    setFieldValue(els.name, row.community_name);
    setFieldValue(els.population, row.population);
    setFieldValue(els.areaSqmile, row.area_sqmile);
    setFieldValue(els.areaSqkm, row.area_sqkm);
    setFieldValue(els.densitySqmi, row.density_per_sqmi);
    setFieldValue(els.densitySqkm, row.density_per_sqkm);
    els.code.disabled = true;
    els.dialogEyebrow.textContent = "Update";
    els.dialogTitle.textContent = `Edit ${row.community_name}`;
    els.saveButton.textContent = "Save changes";
    els.dialog.showModal();
    els.name.focus();
  }

  function closeDialog() {
    if (els.dialog.open) els.dialog.close();
    setFormError("");
  }

  function payloadFromForm() {
    return {
      community_name: els.name.value.trim(),
      population: numberOrNull(els.population.value),
      area_sqmile: numberOrNull(els.areaSqmile.value),
      area_sqkm: numberOrNull(els.areaSqkm.value),
      density_per_sqmi: numberOrNull(els.densitySqmi.value),
      density_per_sqkm: numberOrNull(els.densitySqkm.value),
    };
  }

  async function saveCommunity(event) {
    event.preventDefault();
    setFormError("");

    const payload = payloadFromForm();
    if (payload.community_name.length < 2) {
      setFormError("Community name must be at least 2 characters.");
      return;
    }

    let method = "PUT";
    let url = `${API_BASE}/${state.editingCode}`;

    if (state.editingCode === null) {
      const code = Number(els.code.value);
      if (!Number.isInteger(code) || code <= 0) {
        setFormError("Community code must be a positive whole number.");
        return;
      }
      payload.community_code = code;
      method = "POST";
      url = API_BASE;
    }

    els.saveButton.disabled = true;
    els.saveButton.textContent = "Saving…";

    try {
      const response = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await readError(response));
      }

      const saved = await response.json();
      closeDialog();
      await loadCommunities();
      showToast(
        state.editingCode === null
          ? `Created ${saved.community_name}.`
          : `Updated ${saved.community_name}.`
      );
    } catch (error) {
      setFormError(error.message || "Could not save the community row.");
    } finally {
      els.saveButton.disabled = false;
      els.saveButton.textContent =
        state.editingCode === null ? "Create community" : "Save changes";
    }
  }

  async function deleteCommunity(communityCode, communityName) {
    const confirmed = window.confirm(
      `Delete community ${communityCode} (${communityName})? This cannot be undone.`
    );
    if (!confirmed) return;

    try {
      const response = await fetch(`${API_BASE}/${communityCode}`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(await readError(response));
      }
      await loadCommunities();
      showToast(`Deleted ${communityName}.`);
    } catch (error) {
      showToast(error.message || "Could not delete the community row.", true);
    }
  }

  async function patchCommunityName(communityCode, currentName) {
    const nextName = window.prompt(
      `PATCH community_name for code ${communityCode}:`,
      currentName
    );
    if (nextName === null) return;

    const trimmed = nextName.trim();
    if (trimmed.length < 2) {
      showToast("The new name must be at least 2 characters.", true);
      return;
    }
    if (trimmed === currentName) return;

    try {
      const response = await fetch(`${API_BASE}/${communityCode}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ community_name: trimmed }),
      });
      if (!response.ok) {
        throw new Error(await readError(response));
      }
      await loadCommunities();
      showToast(`Patched community name to ${trimmed}.`);
    } catch (error) {
      showToast(error.message || "Could not patch the community row.", true);
    }
  }

  els.addButton.addEventListener("click", openCreateDialog);
  els.closeButton.addEventListener("click", closeDialog);
  els.cancelButton.addEventListener("click", closeDialog);
  els.form.addEventListener("submit", saveCommunity);

  els.dialog.addEventListener("click", (event) => {
    if (event.target === els.dialog) closeDialog();
  });

  els.tbody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;

    const code = Number(button.dataset.code);
    const name = button.dataset.name || "";
    if (button.dataset.action === "edit") openEditDialog(code);
    if (button.dataset.action === "patch") patchCommunityName(code, name);
    if (button.dataset.action === "delete") deleteCommunity(code, name);
  });

  let searchTimer = null;
  els.search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = els.search.value.trim();
      loadCommunities().catch((error) => {
        showToast(error.message || "Could not load community rows.", true);
      });
    }, 220);
  });

  loadCommunities().catch((error) => {
    showToast(error.message || "Could not load community rows.", true);
  });
})();
