
import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Clock, Plus, RefreshCw, Trash2 } from "lucide-react";
import { apiGet, apiPost, asArray, formatPKR } from "./api";


type BankAccount = {
  id: number;
  name: string;
  bank_name: string;
  account_number: string;
  ledger_account_id: number;
};

type LedgerAccount = {
  id: number;
  code: string;
  name: string;
  account_type: string;
  is_active: boolean;
};

type Adjustment = {
  adjustment_type: string;
  description: string;
  amount: string;
  effect: string;
  counter_account_id: string;
};

type SmartPreview = {
  account_id: number;
  statement_date: string;
  original_cash_book_balance: number;
  adjusted_cash_book_balance: number;
  original_bank_statement_balance: number;
  adjusted_bank_statement_balance: number;
  difference: number;
  status: string;
  book_adjustments_total: number;
  timing_adjustments_total: number;
  adjustments: Adjustment[];
};

type SmartHistory = {
  id: number;
  bank_account_id: number;
  bank_account_name: string;
  statement_date: string;
  original_cash_book_balance: number;
  adjusted_cash_book_balance: number;
  original_bank_statement_balance: number;
  adjusted_bank_statement_balance: number;
  difference: number;
  status: string;
  notes: string | null;
  posted_journal_entry_id: number | null;
  approved_at: string | null;
  created_at: string;
  adjustments: {
    id: number;
    adjustment_type: string;
    description: string;
    amount: number;
    effect: string;
    counter_account_id: number | null;
    journal_entry_id: number | null;
  }[];
};

const adjustmentTypes = [
  "bank_charges",
  "bank_interest",
  "dividend_collected",
  "dishonoured_cheque",
  "direct_debit",
  "cash_book_error",
  "deposit_in_transit",
  "unpresented_cheque",
  "other",
];

const fixedEffects: Record<string, string> = {
  bank_charges: "book_decrease",
  bank_interest: "book_increase",
  dividend_collected: "book_increase",
  dishonoured_cheque: "book_decrease",
  direct_debit: "book_decrease",
  deposit_in_transit: "timing_increase",
  unpresented_cheque: "timing_decrease",
};

function todayLocal() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

function newAdjustment(): Adjustment {
  return {
    adjustment_type: "bank_charges",
    description: "",
    amount: "",
    effect: "book_decrease",
    counter_account_id: "",
  };
}

function isBookEffect(effect: string) {
  return effect === "book_increase" || effect === "book_decrease";
}

export default function SmartReconciliationPanel() {
  const [banks, setBanks] = useState<BankAccount[]>([]);
  const [accounts, setAccounts] = useState<LedgerAccount[]>([]);
  const [history, setHistory] = useState<SmartHistory[]>([]);

  const [accountId, setAccountId] = useState("");
  const [statementDate, setStatementDate] = useState(todayLocal());
  const [cashBookBalance, setCashBookBalance] = useState("");
  const [bankStatementBalance, setBankStatementBalance] = useState("");
  const [notes, setNotes] = useState("");
  const [adjustments, setAdjustments] = useState<Adjustment[]>([]);

  const [preview, setPreview] = useState<SmartPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedBank = banks.find(
    (bank) => String(bank.id) === accountId,
  );

  const availableAccounts = accounts.filter(
    (account) =>
      account.is_active &&
      account.id !== selectedBank?.ledger_account_id,
  );

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [bankData, accountData, historyData] = await Promise.all([
        apiGet<any>("/api/bank/accounts"),
        apiGet<any>("/api/accounts"),
        apiGet<any>("/api/reconciliation/smart"),
      ]);

      const bankList = asArray(bankData) as BankAccount[];
      setBanks(bankList);
      setAccounts(asArray(accountData) as LedgerAccount[]);
      setHistory(asArray(historyData) as SmartHistory[]);

      setAccountId((current) => {
        if (current && bankList.some((bank) => String(bank.id) === current)) {
          return current;
        }
        return bankList.length ? String(bankList[0].id) : "";
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load Smart BRS data.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function updateAdjustment(index: number, changes: Partial<Adjustment>) {
    setAdjustments((current) =>
      current.map((item, i) =>
        i === index ? { ...item, ...changes } : item,
      ),
    );
    setPreview(null);
  }

  function changeAdjustmentType(index: number, type: string) {
    const effect = fixedEffects[type];

    updateAdjustment(index, {
      adjustment_type: type,
      ...(effect ? { effect, counter_account_id: "" } : {}),
    });
  }

  function buildPayload() {
    return {
      account_id: Number(accountId),
      statement_date: statementDate,
      cash_book_balance: Number(cashBookBalance),
      bank_statement_balance: Number(bankStatementBalance),
      notes: notes.trim() || null,
      adjustments: adjustments.map((item) => ({
        adjustment_type: item.adjustment_type,
        description: item.description.trim(),
        amount: Number(item.amount),
        effect: item.effect,
        counter_account_id: isBookEffect(item.effect)
          ? Number(item.counter_account_id)
          : null,
      })),
    };
  }

  function validateForm() {
    if (!accountId || !statementDate) {
      setError("Select a bank account and statement date.");
      return false;
    }

    const cash = Number(cashBookBalance);
    const bank = Number(bankStatementBalance);

    if (
      cashBookBalance.trim() === "" ||
      bankStatementBalance.trim() === "" ||
      !Number.isFinite(cash) ||
      !Number.isFinite(bank) ||
      cash < 0 ||
      bank < 0
    ) {
      setError("Enter valid non-negative opening balances.");
      return false;
    }

    for (const item of adjustments) {
      const amount = Number(item.amount);

      if (
        item.description.trim().length < 2 ||
        !Number.isFinite(amount) ||
        amount <= 0
      ) {
        setError("Every adjustment needs a description and positive amount.");
        return false;
      }

      if (isBookEffect(item.effect) && !item.counter_account_id) {
        setError(
          `Select a counter account for: ${item.description}`,
        );
        return false;
      }
    }

    return true;
  }

  async function previewReconciliation(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setPreview(null);

    if (!validateForm()) return;

    setPreviewing(true);

    try {
      const result = await apiPost<SmartPreview>(
        "/api/reconciliation/smart/preview",
        buildPayload(),
      );

      setPreview(result);
      setSuccess("Smart BRS preview calculated successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to calculate preview.",
      );
    } finally {
      setPreviewing(false);
    }
  }

  async function createDraft() {
    if (!preview || !validateForm()) return;

    setError("");
    setSuccess("");
    setSaving(true);

    try {
      const result = await apiPost<SmartHistory>(
        "/api/reconciliation/smart",
        buildPayload(),
      );

      setSuccess(
        `Smart BRS draft #${result.id} saved. No journal has been posted.`,
      );
      setPreview(null);
      setCashBookBalance("");
      setBankStatementBalance("");
      setNotes("");
      setAdjustments([]);

      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save Smart BRS draft.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function approveReconciliation(id: number) {
    const item = history.find((record) => record.id === id);

    if (!item || item.approved_at || item.posted_journal_entry_id) return;

    const confirmed = window.confirm(
      `Approve Smart BRS #${id}? This may post balanced journal entries to your ledger. This action cannot be repeated.`,
    );

    if (!confirmed) return;

    setError("");
    setSuccess("");
    setApprovingId(id);

    try {
      const result = await apiPost<any>(
        `/api/reconciliation/smart/${id}/approve`,
        {},
      );

      const journalId = result.primary_journal_entry_id;

      setSuccess(
        result.posting_status === "posted"
          ? `Smart BRS #${id} approved. Journal entry #${journalId} posted.`
          : `Smart BRS #${id} approved. No journal entry was required for timing-only adjustments.`,
      );

      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to approve reconciliation.",
      );
    } finally {
      setApprovingId(null);
    }
  }

  return (
    <section className="content-card">
      <div className="section-heading">
        <div>
          <h2>Smart Bank Reconciliation (Smart BRS)</h2>
          <p>
            Calculate book and statement adjustments, save a draft, and
            explicitly approve journal posting.
          </p>
        </div>

        <button
          className="secondary-button"
          type="button"
          onClick={() => void loadData()}
          disabled={loading}
        >
          <RefreshCw size={15} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="error-message">
          <AlertCircle size={17} />
          {error}
        </div>
      )}

      {success && (
        <div className="success-message">
          <CheckCircle2 size={17} />
          {success}
        </div>
      )}

      <form className="module-form" onSubmit={previewReconciliation}>
        <h3>New Smart BRS draft</h3>

        <div className="form-grid">
          <label>
            Bank account
            <select
              value={accountId}
              onChange={(event) => {
                setAccountId(event.target.value);
                setPreview(null);
              }}
              required
            >
              <option value="">Select bank account</option>
              {banks.map((bank) => (
                <option key={bank.id} value={bank.id}>
                  {bank.name} — {bank.bank_name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Statement date
            <input
              type="date"
              value={statementDate}
              onChange={(event) => {
                setStatementDate(event.target.value);
                setPreview(null);
              }}
              required
            />
          </label>

          <label>
            Cash book balance (PKR)
            <input
              type="number"
              min="0"
              step="0.01"
              value={cashBookBalance}
              onChange={(event) => {
                setCashBookBalance(event.target.value);
                setPreview(null);
              }}
              required
            />
          </label>

          <label>
            Bank statement balance (PKR)
            <input
              type="number"
              min="0"
              step="0.01"
              value={bankStatementBalance}
              onChange={(event) => {
                setBankStatementBalance(event.target.value);
                setPreview(null);
              }}
              required
            />
          </label>

          <label>
            Notes (optional)
            <input
              type="text"
              value={notes}
              onChange={(event) => {
                setNotes(event.target.value);
                setPreview(null);
              }}
              placeholder="Reconciliation notes"
            />
          </label>
        </div>

        <div className="section-heading">
          <div>
            <h3>Adjustments</h3>
            <p>
              Add book adjustments or timing differences. Counter accounts
              are required only for book adjustments.
            </p>
          </div>

          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setAdjustments((current) => [...current, newAdjustment()]);
              setPreview(null);
            }}
          >
            <Plus size={15} />
            Add adjustment
          </button>
        </div>

        {adjustments.length === 0 && (
          <p className="empty-state">
            No adjustments added. You can preview the balances without
            adjustments.
          </p>
        )}

        {adjustments.map((item, index) => (
          <div className="content-card" key={index}>
            <div className="section-heading">
              <h3>Adjustment {index + 1}</h3>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setAdjustments((current) =>
                    current.filter((_, i) => i !== index),
                  );
                  setPreview(null);
                }}
              >
                <Trash2 size={15} />
                Remove
              </button>
            </div>

            <div className="form-grid">
              <label>
                Adjustment type
                <select
                  value={item.adjustment_type}
                  onChange={(event) =>
                    changeAdjustmentType(index, event.target.value)
                  }
                >
                  {adjustmentTypes.map((type) => (
                    <option key={type} value={type}>
                      {type.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Description
                <input
                  type="text"
                  minLength={2}
                  value={item.description}
                  onChange={(event) =>
                    updateAdjustment(index, {
                      description: event.target.value,
                    })
                  }
                  required
                />
              </label>

              <label>
                Amount (PKR)
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={item.amount}
                  onChange={(event) =>
                    updateAdjustment(index, { amount: event.target.value })
                  }
                  required
                />
              </label>

              <label>
                Effect
                <select
                    value={item.effect}
                    disabled={Boolean(fixedEffects[item.adjustment_type])}
                    onChange={(event) =>
                        updateAdjustment(index, {
                        effect: event.target.value,
                        counter_account_id: "",
                            })
                        }
                        >
                  <option value="book_increase">Book increase</option>
                  <option value="book_decrease">Book decrease</option>
                  <option value="timing_increase">Timing increase</option>
                  <option value="timing_decrease">Timing decrease</option>
                </select>
              </label>

              {isBookEffect(item.effect) && (
                <label>
                  Counter ledger account
                  <select
                    value={item.counter_account_id}
                    onChange={(event) =>
                      updateAdjustment(index, {
                        counter_account_id: event.target.value,
                      })
                    }
                    required
                  >
                    <option value="">Select counter account</option>
                    {availableAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.code} — {account.name} ({account.account_type})
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>
        ))}

        <button
          className="primary-button"
          type="submit"
          disabled={loading || previewing || saving || !banks.length}
        >
          {previewing ? "Calculating..." : "Calculate Smart BRS preview"}
        </button>
      </form>

      {preview && (
        <div className="content-card">
          <div className="section-heading">
            <div>
              <h3>Reconciliation preview</h3>
              <p>Review these calculated figures before saving the draft.</p>
            </div>
            <span
              className={`status-badge ${
                preview.status === "matched" ? "matched" : "unmatched"
              }`}
            >
              {preview.status}
            </span>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <span>Adjusted cash book</span>
              <h2>{formatPKR(preview.adjusted_cash_book_balance)}</h2>
            </div>
            <div className="stat-card">
              <span>Adjusted bank statement</span>
              <h2>{formatPKR(preview.adjusted_bank_statement_balance)}</h2>
            </div>
            <div className="stat-card">
              <span>Difference</span>
              <h2>{formatPKR(preview.difference)}</h2>
            </div>
            <div className="stat-card">
              <span>Book adjustments</span>
              <h2>{formatPKR(preview.book_adjustments_total)}</h2>
            </div>
            <div className="stat-card">
              <span>Timing adjustments</span>
              <h2>{formatPKR(preview.timing_adjustments_total)}</h2>
            </div>
          </div>

          <p className="empty-state">
            Saving creates a draft only. No journal entry will be posted until
            you approve the saved reconciliation.
          </p>

          <button
            className="primary-button"
            type="button"
            onClick={() => void createDraft()}
            disabled={saving}
          >
            {saving ? "Saving draft..." : "Save Smart BRS draft"}
          </button>
        </div>
      )}

      <div className="section-heading">
        <div>
          <h3>Smart BRS history</h3>
          <p>Review saved drafts, approvals, adjustments, and journal links.</p>
        </div>
        <Clock size={18} />
      </div>

      {loading ? (
        <div className="empty-state">Loading Smart BRS history...</div>
      ) : history.length === 0 ? (
        <div className="empty-state">No Smart BRS records found.</div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Bank account</th>
                <th>Date</th>
                <th>Adjusted book</th>
                <th>Adjusted statement</th>
                <th>Difference</th>
                <th>Status</th>
                <th>Approval</th>
                <th>Journal</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id}>
                  <td>#{item.id}</td>
                  <td>{item.bank_account_name}</td>
                  <td>{item.statement_date}</td>
                  <td>{formatPKR(item.adjusted_cash_book_balance)}</td>
                  <td>{formatPKR(item.adjusted_bank_statement_balance)}</td>
                  <td>{formatPKR(item.difference)}</td>
                  <td>
                    <span
                      className={`status-badge ${
                        item.status === "matched" ? "matched" : "unmatched"
                      }`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.approved_at || item.posted_journal_entry_id ? (
                      <span className="matched-label">
                        <CheckCircle2 size={14} />
                        Approved
                      </span>
                    ) : (
                      <span className="status-badge unmatched">Pending</span>
                    )}
                  </td>
                  <td>
                    {item.posted_journal_entry_id
                      ? `#${item.posted_journal_entry_id}`
                      : "—"}
                  </td>
                  <td>
                    {!item.approved_at && !item.posted_journal_entry_id ? (
                      <button
                        className="primary-button"
                        type="button"
                        onClick={() => void approveReconciliation(item.id)}
                        disabled={approvingId !== null}
                      >
                        {approvingId === item.id ? "Approving..." : "Approve"}
                      </button>
                    ) : (
                      <span className="matched-label">Completed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {history.some((item) => item.adjustments.length > 0) && (
        <div className="content-card">
          <h3>Saved adjustment details</h3>
          {history
            .filter((item) => item.adjustments.length > 0)
            .map((item) => (
              <details key={item.id}>
                <summary>
                  Smart BRS #{item.id} — {item.bank_account_name} —{" "}
                  {item.statement_date}
                </summary>
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Description</th>
                        <th>Amount</th>
                        <th>Effect</th>
                        <th>Counter account</th>
                        <th>Journal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.adjustments.map((adjustment) => (
                        <tr key={adjustment.id}>
                          <td>{adjustment.adjustment_type}</td>
                          <td>{adjustment.description}</td>
                          <td>{formatPKR(adjustment.amount)}</td>
                          <td>{adjustment.effect}</td>
                          <td>
                            {adjustment.counter_account_id ?? "—"}
                          </td>
                          <td>
                            {adjustment.journal_entry_id
                              ? `#${adjustment.journal_entry_id}`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
        </div>
      )}
    </section>
  );
}
