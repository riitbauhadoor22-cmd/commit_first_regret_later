// month-recap.js — the month-end recap pop-up: the first time the app opens in a new month, a short look back at
// LAST month (GET /api/month-recap): saved vs the monthly target, total savings now, money left over.
// Shown once: it is marked as seen as soon as it appears. "Move Rs X to savings?" Yes = POST /api/month-recap/move
// (the server works out X again and saves it as last month's saving). Encouraging texts only (recap.status.*).

async function startMonthRecap() {
  let recap;
  try {
    recap = await getMonthRecap();
  } catch (error) {
    return; // the recap is a bonus: never block the app
  }
  if (!recap.show) return;
  drawMonthRecap(recap);
  openSheet("sheet-recap");
  byId("recap-later").focus();
  markMonthRecapSeen().catch(() => {});
}

function drawMonthRecap(recap) {
  const money = (amount) => (amount < 0 ? formatOut(Math.round(amount)) : formatMoney(Math.round(amount)));
  byId("recap-title").textContent = t("recap.title", { month: formatMonthName(recap.month) });
  const params = { saved: formatMoney(Math.round(Math.max(recap.saved || 0, 0))),
    target: recap.target ? formatMoney(Math.round(recap.target)) : "" };
  byId("recap-status").textContent = t("recap.status." + recap.status, params);
  byId("recap-saved").textContent = recap.saved === null ? "—"
    : recap.target ? t("common.amountOf", { a: money(recap.saved), b: formatMoney(Math.round(recap.target)) })
      : money(recap.saved);
  byId("recap-total").textContent = recap.total_savings === null ? "—" : formatMoney(Math.round(recap.total_savings));
  byId("recap-left-row").hidden = recap.left_over === null; // no income → no left-over line
  if (recap.left_over !== null) byId("recap-left").textContent = money(recap.left_over);
  const canMove = Boolean(recap.move_amount);
  byId("recap-move-text").hidden = !canMove;
  byId("recap-yes").hidden = !canMove;
  if (canMove) byId("recap-move-text").textContent = t("recap.move", { amount: formatMoney(recap.move_amount) });
  setText(byId("recap-later"), canMove ? "recap.notNow" : "common.close");
  byId("recap-error").textContent = "";
  byId("recap-yes").onclick = () => moveLeftOver(recap);
}

async function moveLeftOver(recap) {
  const button = byId("recap-yes");
  button.disabled = true;
  try {
    const data = await moveMonthRecapLeftOver();
    closeSheet("sheet-recap");
    showToast(t("recap.moved", { amount: formatMoney(data.moved), month: formatMonthName(recap.month) }));
    await Promise.all([reloadAfterSaving(), loadDashboard()]);
  } catch (error) {
    showFormError("recap-error", error.message);
  } finally {
    button.disabled = false;
  }
}
