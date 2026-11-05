
import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Save, RefreshCw, BookOpen } from "lucide-react";
import { apiGet, apiPost, asArray, formatPKR } from "./api";

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
            <p>{entries.length} entries available</p>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">Loading journal records...</div>
        ) : entries.length === 0 ? (
          <div className="empty-state">No posted journal entries found.</div>
        ) : (
          <div className="journal-record-list">
            {entries.map((entry) => {
              const debit = entry.lines.reduce(
                (sum, line) => sum + Number(line.debit || 0),
                0,
              );

              return (
                <article className="journal-record" key={entry.id}>
                  <div className="journal-record-top">
                    <div>
                      <strong>{entry.entry_number}</strong>
                      <span>{entry.entry_date}</span>
                    </div>
                    <span className="journal-posted">{entry.status}</span>
                  </div>

                  <p>{entry.description}</p>

                  {entry.reference && (
                    <small>Reference: {entry.reference}</small>
                  )}

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
