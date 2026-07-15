/**
 * Shared formatting helpers for Finance Tracker.
 * Included in layout.html so available on every page.
 */

function formatPence(pence) {
    const pounds = Math.abs(pence) / 100;
    return "£" + pounds.toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatPenceSigned(pence) {
    const sign = pence >= 0 ? "+" : "−";
    const colourClass = pence >= 0 ? "text-emerald-400" : "text-red-400";
    return { text: sign + formatPence(pence), colourClass };
}

function formatDate(isoDate) {
    if (!isoDate) return "—";
    const [year, month, day] = isoDate.split("-");
    return `${day}/${month}/${year}`;
}

/**
 * Format a SQLite datetime string (YYYY-MM-DD HH:MM:SS) as DD/MM/YYYY HH:MM
 */
function formatTimestamp(ts) {
    if (!ts) return "—";

    // 1. Convert "YYYY-MM-DD HH:MM:SS" to "YYYY-MM-DDTHH:MM:SSZ"
    // The 'T' is the ISO separator, the 'Z' tells JS it is UTC.
    const isoStr = ts.includes("T") ? ts : ts.replace(" ", "T") + "Z";
    
    const date = new Date(isoStr);

    // 2. Fallback if the string format is unexpected
    if (isNaN(date.getTime())) return ts;

    // 3. Format using the browser's locale (en-GB for DD/MM/YYYY)
    // This step automatically adds +1 hour for BST or +0 for GMT.
    return date.toLocaleString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    }).replace(',', ''); 
}

function formatInputPreview(rawValue) {
    const num = parseFloat(rawValue);
    if (isNaN(num) || rawValue === "") return "";
    return "£" + num.toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function attachAmountPreview(inputId, previewId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    if (!input || !preview) return;

    input.addEventListener("input", () => {
        const formatted = formatInputPreview(input.value);
        if (formatted) {
            preview.textContent = formatted;
            preview.classList.remove("hidden");
        } else {
            preview.textContent = "";
            preview.classList.add("hidden");
        }
    });
}
