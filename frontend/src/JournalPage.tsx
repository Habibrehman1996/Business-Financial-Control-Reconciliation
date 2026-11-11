
import { useEffect, useMemo, useState } from "react";
import {
  Plus,
  Trash2,
  Save,
  RefreshCw,
  BookOpen,
  RotateCcw,
  Download,
} from "lucide-react";
import { apiGet, apiPost, asArray, formatPKR } from "./api";
import * as XLSX from "xlsx";

type Account = {
  id: number;
  code: string;
  name: string;
  account_type: string;
  is_active: boolean;
};

type JournalLine = {
  account_id: string;
  debit: string;
  credit: string;
  description: string;
};

type JournalEntry = {
  id: number;
  entry_number: string;
  entry_date: string;
  description: string;
  reference: string | null;
  status: string;
  source_type: string;
  reversal_of_id: number | null;
  lines: {
    id: number;
    account_id: number;
    debit: string;
    credit: string;
    description: string | null;
  }[];
};

const newLine = (): JournalLine => ({
  account_id: "",
  debit: "",
  credit: "",
  description: "",
});

function today() {
  const date = new Date();
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000)
    .toISOString()
    .slice(0, 10);
}

export default function JournalPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [entryDate, setEntryDate] = useState(today());
  const [description, setDescription] = useState("");
  const [reference, setReference] = useState("");
  const [lines, setLines] = useState<JournalLine[]>([
    newLine(),
    newLine(),
  ]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [reversingId, setReversingId] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [reversalFilter, setReversalFilter] = useState("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const totalDebit = useMemo(
    () => lines.reduce((sum, line) => sum + (Number(line.debit) || 0), 0),
    [lines],
  );

  const totalCredit = useMemo(
    () => lines.reduce((sum, line) => sum + (Number(line.credit) || 0), 0),
    [lines],
  );

  const balanced =
    totalDebit > 0 &&
    Math.abs(totalDebit - totalCredit) < 0.000001;
  const filteredEntries = useMemo(() => {
  return entries.filter((entry) => {
    const search = searchTerm.trim().toLowerCase();

    const matchesSearch =
      !search ||
      entry.entry_number.toLowerCase().includes(search) ||
      entry.description.toLowerCase().includes(search) ||
      (entry.reference || "").toLowerCase().includes(search);

    const matchesSource =
      sourceFilter === "all" || entry.source_type === sourceFilter;

    const hasBeenReversed = entries.some(
      (item) => item.reversal_of_id === entry.id
    );

    const isReversal = entry.reversal_of_id !== null;

    const matchesReversal =
      reversalFilter === "all" ||
      (reversalFilter === "reversed" && hasBeenReversed) ||
      (reversalFilter === "not_reversed" && !hasBeenReversed && !isReversal) ||
      (reversalFilter === "reversal_entry" && isReversal);

    const matchesStartDate =
      !startDate || entry.entry_date >= startDate;

    const matchesEndDate =
      !endDate || entry.entry_date <= endDate;

    return (
      matchesSearch &&
      matchesSource &&
      matchesReversal &&
      matchesStartDate &&
      matchesEndDate
    );
  });
}, [entries, searchTerm, sourceFilter, reversalFilter, startDate, endDate]);
  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [accountData, journalData] = await Promise.all([
        apiGet("/api/accounts"),
        apiGet("/api/journal"),
      ]);

      setAccounts(asArray(accountData));
      setEntries(asArray(journalData));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load journal data.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  function updateLine(
    index: number,
    field: keyof JournalLine,
    value: string,
  ) {
    setLines((current) =>
      current.map((line, i) => {
        if (i !== index) return line;

        const updated = { ...line, [field]: value };

        if (field === "debit" && Number(value) > 0) {
          updated.credit = "";
        }

        if (field === "credit" && Number(value) > 0) {
          updated.debit = "";
        }

        return updated;
      }),
    );
  }

  function addLine() {
    setLines((current) => [...current, newLine()]);
  }

  function removeLine(index: number) {
    if (lines.length <= 2) return;

    setLines((current) => current.filter((_, i) => i !== index));
  }

  function resetForm() {
    setEntryDate(today());
    setDescription("");
    setReference("");
    setLines([newLine(), newLine()]);
  }

  async function submitEntry(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!description.trim()) {
      setError("Journal description is required.");
      return;
    }

    if (lines.length < 2) {
      setError("At least two journal lines are required.");
      return;
    }

    const preparedLines = lines.map((line) => ({
      account_id: Number(line.account_id),
      debit: Number(line.debit || 0),
      credit: Number(line.credit || 0),
      description: line.description.trim() || null,
    }));

    const invalidLine = preparedLines.some(
      (line) =>
        !line.account_id ||
        (line.debit > 0) === (line.credit > 0),
    );

    if (invalidLine) {
      setError(
        "Har line mein account select karein aur Debit ya Credit mein se sirf ek amount enter karein.",
      );
      return;
    }

    if (!balanced) {
      setError("Total Debit aur Total Credit barabar hone chahiye.");
      return;
    }

    setSaving(true);

    try {
      const result = await apiPost<JournalEntry>("/api/journal", {
        entry_date: entryDate,
        description: description.trim(),
        reference: reference.trim() || null,
        lines: preparedLines,
      });

      setSuccess(
        `Journal entry ${result.entry_number} successfully posted.`,
      );

      resetForm();
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save journal entry.",
      );
    } finally {
      setSaving(false);
    }
  }
  async function reverseEntry(entry: JournalEntry) {
    const confirmed = window.confirm(
      `Are you sure you want to reverse journal entry ${entry.entry_number}? This action cannot be undone.`
    );

    if (!confirmed) return;

    setError("");
    setSuccess("");
    setReversingId(entry.id);

    try {
      const result = await apiPost<JournalEntry>(
        `/api/journal/${entry.id}/reverse`,
        {}
      );

      await loadData();

      setSuccess(
        `Journal entry ${entry.entry_number} successfully reversed. Reversal: ${result.entry_number}.`
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reverse journal entry."
      );
    } finally {
      setReversingId(null);
    }
  }
    function exportJournalCSV() {
    if (filteredEntries.length === 0) {
      setError("No journal records available to export.");
      return;
    }

    const headers = [
      "Entry Number",
      "Date",
      "Description",
      "Reference",
      "Source",
      "Status",
      "Reversal Of ID",
      "Account Code & Name",
      "Line Description",
      "Debit",
      "Credit",
    ];

    const rows = filteredEntries.flatMap((entry) =>
      entry.lines.map((line) => {
        const account = accounts.find(
          (item) => item.id === line.account_id
        );

        return [
          entry.entry_number,
          entry.entry_date,
          entry.description,
          entry.reference || "",
          entry.source_type,
          entry.status,
          entry.reversal_of_id ?? "",
          account
            ? `${account.code} - ${account.name}`
            : `Account #${line.account_id}`,
          line.description || "",
          line.debit,
          line.credit,
        ];
      })
    );

    const escapeCSV = (value: string | number) =>
      `"${String(value).replace(/"/g, '""')}"`;

    const csvContent = [
      headers.map(escapeCSV).join(","),
      ...rows.map((row) => row.map(escapeCSV).join(",")),
    ].join("\r\n");

    const blob = new Blob(["\uFEFF", csvContent], {
      type: "text/csv;charset=utf-8;",
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `journal-entries-${today()}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setSuccess("Journal CSV exported successfully.");
    setError("");
  }
    function exportJournalExcel() {
    if (filteredEntries.length === 0) {
      setError("No journal records available to export.");
      return;
    }

    const rows = filteredEntries.flatMap((entry) =>
      entry.lines.map((line) => ({
        "Entry Number": entry.entry_number,
        Date: entry.entry_date,
        Description: entry.description,
        Reference: entry.reference || "",
        Source:
          entry.source_type === "manual"
            ? "Manual Entry"
            : "System Generated",
        Status: entry.status,
        "Reversal Of ID": entry.reversal_of_id ?? "",
        "Account Code": accounts.find(
          (item) => item.id === line.account_id
        )?.code || "",
        "Account Name": accounts.find(
          (item) => item.id === line.account_id
        )?.name || `Account #${line.account_id}`,
        "Line Description": line.description || "",
        Debit: Number(line.debit || 0),
        Credit: Number(line.credit || 0),
      }))
    );

    const worksheet = XLSX.utils.json_to_sheet(rows);

    worksheet["!cols"] = [
      { wch: 22 },
      { wch: 14 },
      { wch: 35 },
      { wch: 20 },
      { wch: 20 },
      { wch: 12 },
      { wch: 16 },
      { wch: 15 },
      { wch: 25 },
      { wch: 30 },
      { wch: 16 },
      { wch: 16 },
    ];

    const workbook = XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
      workbook,
      worksheet,
      "Journal Entries"
    );

    XLSX.writeFile(
      workbook,
      `journal-entries-${today()}.xlsx`
    );

    setSuccess("Journal Excel file exported successfully.");
    setError("");
  }
  function accountName(accountId: number) {
    const account = accounts.find((item) => item.id === accountId);
    return account
      ? `${account.code} - ${account.name}`
      : `Account #${accountId}`;
  }

  return (
    <div className="journal-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ACCOUNTING & LEDGER</span>
          <h1>Journal Entries</h1>
          <p>Create balanced journal entries and review posted records.</p>
        </div>

        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadData()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="journal-success">{success}</div>}

      <form className="panel journal-form" onSubmit={submitEntry}>
        <div className="panel-heading">
          <div>
            <h2><BookOpen size={18} /> Create Journal Entry</h2>
            <p>Enter transactions using double-entry accounting.</p>
          </div>
        </div>

        <div className="journal-fields">
          <label>
            Entry Date
            <input
              type="date"
              value={entryDate}
              onChange={(e) => setEntryDate(e.target.value)}
              required
            />
          </label>

          <label>
            Reference
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="e.g. JV-001"
            />
          </label>

          <label className="journal-description">
            Description
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Enter transaction description"
              minLength={2}
              maxLength={255}
              required
            />
          </label>
        </div>

        <div className="journal-lines-heading">
          <div>
            <h3>Journal Lines</h3>
            <p>Every line must contain either a debit or a credit.</p>
          </div>

          <button
            type="button"
            className="secondary-button"
            onClick={addLine}
          >
            <Plus size={15} /> Add Line
          </button>
        </div>

        <div className="journal-table-wrap">
          <table className="journal-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Description</th>
                <th>Debit (PKR)</th>
                <th>Credit (PKR)</th>
                <th></th>
              </tr>
            </thead>

            <tbody>
              {lines.map((line, index) => (
                <tr key={index}>
                  <td>
                    <select
                      value={line.account_id}
                      onChange={(e) =>
                        updateLine(index, "account_id", e.target.value)
                      }
                      required
                    >
                      <option value="">Select account</option>
                      {accounts.map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.code} - {account.name}
                        </option>
                      ))}
                    </select>
                  </td>

                  <td>
                    <input
                      value={line.description}
                      onChange={(e) =>
                        updateLine(index, "description", e.target.value)
                      }
                      placeholder="Optional"
                    />
                  </td>

                  <td>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.debit}
                      onChange={(e) =>
                        updateLine(index, "debit", e.target.value)
                      }
                      placeholder="0.00"
                    />
                  </td>

                  <td>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.credit}
                      onChange={(e) =>
                        updateLine(index, "credit", e.target.value)
                      }
                      placeholder="0.00"
                    />
                  </td>

                  <td>
                    <button
                      type="button"
                      className="journal-remove"
                      onClick={() => removeLine(index)}
                      disabled={lines.length <= 2}
                      title="Remove line"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="journal-totals">
          <div>
            <span>Total Debit</span>
            <strong>{formatPKR(totalDebit)}</strong>
          </div>

          <div>
            <span>Total Credit</span>
            <strong>{formatPKR(totalCredit)}</strong>
          </div>

          <div className={balanced ? "balanced" : "unbalanced"}>
            <span>{balanced ? "Balanced" : "Difference"}</span>
            <strong>
              {balanced
                ? "Ready to post"
                : formatPKR(Math.abs(totalDebit - totalCredit))}
            </strong>
          </div>
        </div>

        <div className="journal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={resetForm}
          >
            Clear Form
          </button>

          <button
            type="submit"
            className="journal-submit"
            disabled={saving || loading || !balanced}
          >
            <Save size={16} />
            {saving ? "Posting..." : "Post Journal Entry"}
          </button>
        </div>

        {accounts.length === 0 && !loading && (
          <p className="journal-warning">
            No active accounts found. Initialize or create accounts before
            posting a journal entry.
          </p>
        )}
      </form>

      <section className="panel journal-records">
                <div className="panel-heading">
          <div>
            <h2>Posted Journal Records</h2>
            <p>{filteredEntries.length} of {entries.length} entries shown</p>
          </div>

                    <button
            type="button"
            className="secondary-button"
            onClick={exportJournalCSV}
            disabled={loading || filteredEntries.length === 0}
          >
            <Download size={16} />
            Export CSV
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={exportJournalExcel}
            disabled={loading || filteredEntries.length === 0}
          >
            <Download size={16} />
            Export Excel
          </button>
        </div>
                <div className="journal-filters">
          <input
            type="search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search entry number, description or reference..."
          />

          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="all">All Sources</option>
            <option value="manual">Manual Entries</option>
            <option value="system">System Generated</option>
          </select>

          <select
            value={reversalFilter}
            onChange={(e) => setReversalFilter(e.target.value)}
          >
            <option value="all">All Reversal Status</option>
            <option value="reversed">Reversed Original Entries</option>
            <option value="not_reversed">Not Reversed</option>
            <option value="reversal_entry">Reversal Entries</option>
          </select>

          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            aria-label="Start date"
          />

          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            aria-label="End date"
          />

          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setSearchTerm("");
              setSourceFilter("all");
              setReversalFilter("all");
              setStartDate("");
              setEndDate("");
            }}
          >
            Clear Filters
          </button>
        </div>
        {loading ? (
          <div className="empty-state">Loading journal records...</div>
        ) : entries.length === 0 ? (
          <div className="empty-state">No posted journal entries found.</div>
                ) : filteredEntries.length === 0 ? (
          <div className="empty-state">
            No journal entries match the selected filters.
          </div>
        ) : (
          <div className="journal-record-list">
            {filteredEntries.map((entry) => {
              const debit = entry.lines.reduce(
                (sum, line) => sum + Number(line.debit || 0),
                0,
              );
              const hasBeenReversed = entries.some(
                (item) => item.reversal_of_id === entry.id
              );

              return (
                <article className="journal-record" key={entry.id}>
                  <div className="journal-record-top">
                    <div>
                      
                      <strong>{entry.entry_number}</strong>
                      <span>{entry.entry_date}</span>
                    </div>
                    
                    <div className="journal-record-controls">
                      <span className="journal-posted">{entry.status}</span>

                      {entry.source_type === "manual" &&
                        entry.status === "posted" &&
                        entry.reversal_of_id === null &&
                        !hasBeenReversed && (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => void reverseEntry(entry)}
                            disabled={reversingId === entry.id}
                          >
                            <RotateCcw size={15} />
                            {reversingId === entry.id ? "Reversing..." : "Reverse"}
                          </button>
                        )}
                        

                      {hasBeenReversed && (
                        <span className="journal-posted">Reversed</span>
                      )}
                  </div>
                  </div>
                  
                  
                  <p>{entry.description}</p>

                  <div className="journal-audit-info">
                <small>
                  Source: {entry.source_type === "manual" ? "Manual Entry" : "System Generated"}
                </small>

                {entry.reference && (
                  <small>Reference: {entry.reference}</small>
                )}

                {entry.reversal_of_id !== null && (
                  <small>
                    Reversal of Entry ID: #{entry.reversal_of_id}
                  </small>
                )}

                {entries.some((item) => item.reversal_of_id === entry.id) && (
                  <small>
                    Reversed by: {
                      entries.find((item) => item.reversal_of_id === entry.id)?.entry_number
                    }
                  </small>
                )}
              </div>

                  <div className="journal-record-bottom">
                    <span>{entry.lines.length} lines</span>
                    <strong>{formatPKR(debit)}</strong>
                  </div>

                  <div className="journal-record-lines">
                    {entry.lines.map((line) => (
                      <div key={line.id}>
                        <span>{accountName(line.account_id)}</span>
                        <span>
                          {Number(line.debit) > 0
                            ? `Dr ${formatPKR(line.debit)}`
                            : `Cr ${formatPKR(line.credit)}`}
                        </span>
                      </div>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
    
  );
}
