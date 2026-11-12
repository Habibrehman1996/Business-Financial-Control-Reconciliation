
import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  Scale,
  Wallet,
  Landmark,
} from "lucide-react";
import { apiGet, apiPost, asArray, formatPKR } from "./api";
import "./App.css";

type Account = {
  id: number;
  name: string;
  bank_name?: string;
  account_number?: string;
};

type Reconciliation = {
  id: number;
  account_type: "bank" | "cash";
  account_id: number;
  statement_date: string;
  statement_closing_balance: number;
  book_closing_balance: number;
  difference: number;
  status: string;
  notes?: string;
  created_at: string;
};

export default function ReconciliationPage() {
  const [accountType, setAccountType] = useState<"bank" | "cash">("bank");
  const [bankAccounts, setBankAccounts] = useState<Account[]>([]);
  const [cashAccounts, setCashAccounts] = useState<Account[]>([]);
  const [records, setRecords] = useState<Reconciliation[]>([]);

  const [accountId, setAccountId] = useState("");
  const [statementDate, setStatementDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [statementBalance, setStatementBalance] = useState("");
  const [notes, setNotes] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const accounts = accountType === "bank" ? bankAccounts : cashAccounts;

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [banks, cash, history] = await Promise.all([
        apiGet<any>("/api/bank/accounts"),
        apiGet<any>("/api/cash/accounts"),
        apiGet<any>("/api/reconciliation"),
      ]);

      setBankAccounts(asArray(banks));
      setCashAccounts(asArray(cash));
      setRecords(asArray(history));

      const availableAccounts =
        accountType === "bank" ? asArray(banks) : asArray(cash);

      setAccountId((current) => {
        if (
          current &&
          availableAccounts.some((account: Account) => String(account.id) === current)
        ) {
          return current;
        }

        return availableAccounts.length
          ? String(availableAccounts[0].id)
          : "";
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load reconciliation data.",
      );
    } finally {
      setLoading(false);
    }
  }, [accountType]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function submitReconciliation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const balance = Number(statementBalance);

    if (!accountId) {
      setError("Please select an account.");
      return;
    }

    if (!statementDate || !Number.isFinite(balance) || balance < 0) {
      setError("Please enter a valid date and non-negative statement balance.");
      return;
    }

    setSaving(true);

    try {
      await apiPost("/api/reconciliation/" + accountType, {
        account_type: accountType,
        account_id: Number(accountId),
        statement_date: statementDate,
        statement_closing_balance: balance,
        notes: notes.trim() || null,
      });

      setSuccess("Reconciliation completed successfully.");
      setStatementBalance("");
      setNotes("");

      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to complete reconciliation.",
      );
    } finally {
      setSaving(false);
    }
  }

  const matchedCount = records.filter(
    (record) => record.status === "matched",
  ).length;

  const unmatchedCount = records.length - matchedCount;

  return (
    <div className="module-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FINANCIAL CONTROL</span>
          <h1>Reconciliation</h1>
          <p>Compare bank and cash statement balances with your ledger.</p>
        </div>

        <button
          className="secondary-button"
          type="button"
          onClick={() => void loadData()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-heading">
            <span>Total reconciliations</span>
            <Scale size={19} />
          </div>
          <h2>{records.length}</h2>
          <p>Saved reconciliation records</p>
        </div>

        <div className="stat-card">
          <div className="stat-heading">
            <span>Matched</span>
            <CheckCircle2 size={19} />
          </div>
          <h2>{matchedCount}</h2>
          <p>Balances are equal</p>
        </div>

        <div className="stat-card">
          <div className="stat-heading">
            <span>Unmatched</span>
            <AlertCircle size={19} />
          </div>
          <h2>{unmatchedCount}</h2>
          <p>Balances need review</p>
        </div>
      </div>

      <section className="content-card">
        <div className="section-heading">
          <div>
            <h2>New reconciliation</h2>
            <p>Enter the closing balance from your statement.</p>
          </div>
        </div>

        <div className="form-tabs">
          <button
            type="button"
            className={accountType === "bank" ? "active" : ""}
            onClick={() => {
              setAccountType("bank");
              setAccountId("");
              setError("");
              setSuccess("");
            }}
          >
            <Landmark size={17} />
            Bank
          </button>

          <button
            type="button"
            className={accountType === "cash" ? "active" : ""}
            onClick={() => {
              setAccountType("cash");
              setAccountId("");
              setError("");
              setSuccess("");
            }}
          >
            <Wallet size={17} />
            Cash
          </button>
        </div>

        <form className="module-form" onSubmit={submitReconciliation}>
          <div className="form-grid">
            <label>
              {accountType === "bank" ? "Bank account" : "Cash account"}
              <select
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
                required
              >
                <option value="">Select account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                    {account.bank_name ? ` — ${account.bank_name}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Statement date
              <input
                type="date"
                value={statementDate}
                onChange={(event) => setStatementDate(event.target.value)}
                required
              />
            </label>

            <label>
              Statement closing balance (PKR)
              <input
                type="number"
                min="0"
                step="0.01"
                value={statementBalance}
                onChange={(event) => setStatementBalance(event.target.value)}
                placeholder="Enter closing balance"
                required
              />
            </label>

            <label>
              Notes (optional)
              <input
                type="text"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Add reconciliation notes"
              />
            </label>
          </div>

          {error && <div className="error-message">{error}</div>}
          {success && <div className="success-message">{success}</div>}

          <button
            className="primary-button"
            type="submit"
            disabled={saving || loading || !accounts.length}
          >
            {saving ? "Processing..." : "Complete reconciliation"}
          </button>

          {!loading && !accounts.length && (
            <p className="empty-state">
              No active {accountType} accounts found. Create an account first.
            </p>
          )}
        </form>
      </section>

      <section className="content-card">
        <div className="section-heading">
          <div>
            <h2>Reconciliation history</h2>
            <p>Review your previously completed reconciliations.</p>
          </div>
          <Clock size={19} />
        </div>

        {loading ? (
          <div className="empty-state">Loading reconciliation records...</div>
        ) : records.length === 0 ? (
          <div className="empty-state">No reconciliation records found.</div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Account</th>
                  <th>Date</th>
                  <th>Statement balance</th>
                  <th>Book balance</th>
                  <th>Difference</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => {
                  const accountList =
                    record.account_type === "bank" ? bankAccounts : cashAccounts;

                  const account = accountList.find(
                    (item) => item.id === record.account_id,
                  );

                  return (
                    <tr key={record.id}>
                      <td>#{record.id}</td>
                      <td>{record.account_type.toUpperCase()}</td>
                      <td>{account?.name ?? `Account #${record.account_id}`}</td>
                      <td>{record.statement_date}</td>
                      <td>{formatPKR(record.statement_closing_balance)}</td>
                      <td>{formatPKR(record.book_closing_balance)}</td>
                      <td>{formatPKR(record.difference)}</td>
                      <td>
                        <span
                          className={
                            record.status === "matched"
                              ? "status-badge matched"
                              : "status-badge unmatched"
                          }
                        >
                          {record.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
