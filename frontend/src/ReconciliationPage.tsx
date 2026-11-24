
import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  Scale,
  Wallet,
  Landmark,
  Upload,
  FileText,
  Search,
  Link2,
  XCircle,
} from "lucide-react";
import {
  apiGet,
  apiPost,
  apiUpload,
  asArray,
  formatPKR,
} from "./api";
import "./App.css";
import SmartReconciliationPanel from "./SmartReconciliationPanel";

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

type BankStatementLine = {
  id: number;
  bank_account_id: number;
  transaction_date: string;
  description: string;
  reference: string | null;
  amount: string | number;
  direction: string;
  statement_balance: string | number | null;
  matched_bank_transaction_id: number | null;
  match_status: string;
};

type BankTransaction = {
  id: number;
  bank_account_id: number;
  transaction_date: string;
  description: string;
  reference: string | null;
  amount: string | number;
  direction: string;
  source: string;
  is_reconciled: boolean;
};

type MatchCandidate = {
  bank_transaction: BankTransaction;
  confidence: "high" | "medium";
  match_reasons: string[];
};

type MatchPreview = {
  statement_line_id: number;
  match_status:
    | "already_matched"
    | "no_match"
    | "single_candidate"
    | "multiple_candidates";
  candidates: MatchCandidate[];
};

type ImportResult = {
  message: string;
  bank_account_id: number;
  imported_count: number;
  duplicate_count: number;
  skipped_count: number;
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

  // Transaction-level bank reconciliation state
  const [statementLines, setStatementLines] = useState<BankStatementLine[]>([]);
  const [statementFilter, setStatementFilter] = useState<
    "all" | "matched" | "unmatched"
  >("all");
  const [statementLoading, setStatementLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const [activePreview, setActivePreview] = useState<MatchPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState<number | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<
    Record<number, number>
  >({});
  const [matchingLineId, setMatchingLineId] = useState<number | null>(null);

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
          availableAccounts.some(
            (account: Account) => String(account.id) === current,
          )
        ) {
          return current;
        }

        return availableAccounts.length
          ? String(availableAccounts[0].id)
          : "";
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load reconciliation data.",
      );
    } finally {
      setLoading(false);
    }
  }, [accountType]);

  const loadStatementLines = useCallback(async () => {
    if (accountType !== "bank" || !accountId) {
      setStatementLines([]);
      return;
    }

    setStatementLoading(true);

    try {
      const query =
        statementFilter === "all"
          ? ""
          : `?match_status=${statementFilter}`;

      const data = await apiGet<BankStatementLine[]>(
        `/api/bank/accounts/${accountId}/statement/lines${query}`,
      );

      setStatementLines(asArray(data));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load bank statement lines.",
      );
    } finally {
      setStatementLoading(false);
    }
  }, [accountType, accountId, statementFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    void loadStatementLines();
  }, [loadStatementLines]);

  async function submitReconciliation(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const balance = Number(statementBalance);

    if (!accountId) {
      setError("Please select an account.");
      return;
    }

    if (!statementDate || !Number.isFinite(balance) || balance < 0) {
      setError(
        "Please enter a valid date and non-negative statement balance.",
      );
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
        err instanceof Error
          ? err.message
          : "Unable to complete reconciliation.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function uploadStatement(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setImportResult(null);

    if (!accountId) {
      setError("Please select a bank account first.");
      return;
    }

    if (!selectedFile) {
      setError("Please select a CSV statement file.");
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
      setError("Only CSV files are supported.");
      return;
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError("The CSV file must not exceed 10 MB.");
      return;
    }

    setUploading(true);

    try {
      const result = await apiUpload<ImportResult>(
        `/api/bank/accounts/${accountId}/statement/import`,
        selectedFile,
      );

      setImportResult(result);
      setSuccess(result.message || "Bank statement imported successfully.");
      setSelectedFile(null);
      setActivePreview(null);

      const fileInput = document.getElementById(
        "bank-statement-file",
      ) as HTMLInputElement | null;

      if (fileInput) fileInput.value = "";

      await loadStatementLines();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to upload bank statement.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function previewMatch(lineId: number) {
    if (!accountId) return;

    setError("");
    setActivePreview(null);
    setPreviewLoading(lineId);

    try {
      const preview = await apiGet<MatchPreview>(
        `/api/bank/accounts/${accountId}/statement/lines/${lineId}/match-preview?date_tolerance_days=3`,
      );

      setActivePreview(preview);

      if (preview.candidates.length > 0) {
        setSelectedCandidates((current) => ({
          ...current,
          [lineId]: preview.candidates[0].bank_transaction.id,
        }));
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to preview transaction matches.",
      );
    } finally {
      setPreviewLoading(null);
    }
  }

  async function confirmMatch(lineId: number) {
    const transactionId = selectedCandidates[lineId];

    if (!transactionId || !accountId) {
      setError("Please select a matching book transaction.");
      return;
    }

    setError("");
    setSuccess("");
    setMatchingLineId(lineId);

    try {
      await apiPost(
        `/api/bank/accounts/${accountId}/statement/lines/${lineId}/match`,
        {
          bank_transaction_id: transactionId,
        },
      );

      setSuccess(
        `Statement transaction #${lineId} matched successfully.`,
      );

      setActivePreview(null);

      await loadStatementLines();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to confirm transaction match.",
      );
    } finally {
      setMatchingLineId(null);
    }
  }

  const matchedCount = records.filter(
    (record) => record.status === "matched",
  ).length;

  const unmatchedCount = records.length - matchedCount;

  const statementMatchedCount = statementLines.filter(
    (line) => line.match_status === "matched",
  ).length;

  const statementUnmatchedCount = statementLines.filter(
    (line) => line.match_status === "unmatched",
  ).length;

  const statementTotal = statementLines.reduce(
    (total, line) => total + Number(line.amount),
    0,
  );

  return (
    <div className="module-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FINANCIAL CONTROL</span>
          <h1>Reconciliation</h1>
          <p>
            Compare bank and cash statement balances with your ledger and
            match individual transactions.
          </p>
        </div>

        <button
          className="secondary-button"
          type="button"
          onClick={() => {
            void loadData();
            void loadStatementLines();
          }}
          disabled={loading || statementLoading}
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
            <SmartReconciliationPanel />

      {error && (
        <div className="error-message">
          <AlertCircle size={18} />
          <div>
            <strong>Something went wrong</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {success && (
        <div className="success-message">
          <CheckCircle2 size={17} />
          {success}
        </div>
      )}

      {/* Existing reconciliation statistics */}
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

      {/* Transaction-level bank reconciliation */}
      <section className="content-card">
        <div className="section-heading">
          <div>
            <h2>
              <FileText size={19} /> Bank Statement Import
            </h2>
            <p>
              Upload a CSV statement to compare individual bank transactions
              with your accounting ledger.
            </p>
          </div>
        </div>

        <div className="module-form">
          <div className="form-grid">
            <label>
              Bank account
              <select
                value={accountType === "bank" ? accountId : ""}
                onChange={(event) => {
                  setAccountType("bank");
                  setAccountId(event.target.value);
                  setActivePreview(null);
                  setImportResult(null);
                }}
              >
                <option value="">Select bank account</option>
                {bankAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                    {account.bank_name ? ` — ${account.bank_name}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <label>
              CSV statement file
              <input
                id="bank-statement-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) =>
                  setSelectedFile(event.target.files?.[0] ?? null)
                }
              />
            </label>
          </div>

          {selectedFile && (
            <p className="empty-state">
              Selected: {selectedFile.name} (
              {(selectedFile.size / 1024).toFixed(1)} KB)
            </p>
          )}

          <button
            className="primary-button"
            type="button"
            disabled={uploading || !accountId || !selectedFile}
            onClick={() => {
              const form = document.getElementById(
                "bank-upload-form",
              ) as HTMLFormElement | null;

              form?.requestSubmit();
            }}
          >
            <Upload size={16} />
            {uploading ? "Uploading..." : "Upload bank statement"}
          </button>

          <form
            id="bank-upload-form"
            onSubmit={uploadStatement}
            style={{ display: "none" }}
          />
        </div>

        {importResult && (
          <div className="import-summary">
            <strong>Import completed</strong>
            <div className="import-summary-grid">
              <div>
                <span>Imported</span>
                <strong>{importResult.imported_count}</strong>
              </div>
              <div>
                <span>Duplicates</span>
                <strong>{importResult.duplicate_count}</strong>
              </div>
              <div>
                <span>Skipped</span>
                <strong>{importResult.skipped_count}</strong>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Imported statement lines */}
      {accountType === "bank" && (
        <section className="content-card">
          <div className="section-heading">
            <div>
              <h2>Statement Transactions</h2>
              <p>
                Review imported transactions and find matching ledger entries.
              </p>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void loadStatementLines()}
              disabled={statementLoading || !accountId}
            >
              <RefreshCw size={15} />
              Refresh lines
            </button>
          </div>

          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-heading">
                <span>Displayed transactions</span>
                <FileText size={18} />
              </div>
              <h2>{statementLines.length}</h2>
              <p>Loaded statement lines</p>
            </div>

            <div className="stat-card">
              <div className="stat-heading">
                <span>Matched</span>
                <CheckCircle2 size={18} />
              </div>
              <h2>{statementMatchedCount}</h2>
              <p>Successfully linked</p>
            </div>

            <div className="stat-card">
              <div className="stat-heading">
                <span>Unmatched</span>
                <AlertCircle size={18} />
              </div>
              <h2>{statementUnmatchedCount}</h2>
              <p>Need matching review</p>
            </div>
          </div>

          <div className="statement-toolbar">
            <div className="form-tabs">
              <button
                type="button"
                className={statementFilter === "all" ? "active" : ""}
                onClick={() => {
                  setStatementFilter("all");
                  setActivePreview(null);
                }}
              >
                All
              </button>

              <button
                type="button"
                className={statementFilter === "unmatched" ? "active" : ""}
                onClick={() => {
                  setStatementFilter("unmatched");
                  setActivePreview(null);
                }}
              >
                Unmatched
              </button>

              <button
                type="button"
                className={statementFilter === "matched" ? "active" : ""}
                onClick={() => {
                  setStatementFilter("matched");
                  setActivePreview(null);
                }}
              >
                Matched
              </button>
            </div>

            <div className="statement-total">
              Displayed amount: <strong>{formatPKR(statementTotal)}</strong>
            </div>
          </div>

          {statementLoading ? (
            <div className="empty-state">Loading statement transactions...</div>
          ) : !accountId ? (
            <div className="empty-state">
              Select a bank account to view its statement transactions.
            </div>
          ) : statementLines.length === 0 ? (
            <div className="empty-state">
              No statement transactions found for this filter.
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Reference</th>
                    <th>Direction</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {statementLines.map((line) => (
                    <tr key={line.id}>
                      <td>#{line.id}</td>
                      <td>{line.transaction_date}</td>
                      <td>{line.description}</td>
                      <td>{line.reference || "—"}</td>
                      <td>
                        <span
                          className={
                            line.direction === "in"
                              ? "transaction-direction incoming"
                              : "transaction-direction outgoing"
                          }
                        >
                          {line.direction === "in" ? "Incoming" : "Outgoing"}
                        </span>
                      </td>
                      <td>{formatPKR(line.amount)}</td>
                      <td>
                        <span
                          className={`status-badge ${
                            line.match_status === "matched"
                              ? "matched"
                              : "unmatched"
                          }`}
                        >
                          {line.match_status}
                        </span>
                      </td>
                      <td>
                        {line.match_status === "matched" ? (
                          <span className="matched-label">
                            <CheckCircle2 size={15} />
                            Linked
                          </span>
                        ) : (
                          <button
                            className="secondary-button"
                            type="button"
                            onClick={() => void previewMatch(line.id)}
                            disabled={previewLoading === line.id}
                          >
                            <Search size={14} />
                            {previewLoading === line.id
                              ? "Searching..."
                              : "Find match"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Match preview */}
          {activePreview && (
            <div className="match-preview">
              <div className="section-heading">
                <div>
                  <h3>Match Preview — Statement #{activePreview.statement_line_id}</h3>
                  <p>
                    Review the suggested book transactions before confirming.
                  </p>
                </div>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setActivePreview(null)}
                >
                  <XCircle size={15} />
                  Close
                </button>
              </div>

              {activePreview.match_status === "already_matched" && (
                <div className="empty-state">
                  This statement line has already been matched.
                </div>
              )}

              {activePreview.match_status === "no_match" && (
                <div className="empty-state">
                  <AlertCircle size={18} />
                  No eligible book transaction was found. Check the date,
                  amount, direction and reference.
                </div>
              )}

              {activePreview.candidates.length > 0 && (
                <>
                  <p className="candidate-count">
                    {activePreview.candidates.length} candidate(s) found.
                    Select the correct transaction.
                  </p>

                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Select</th>
                          <th>Transaction</th>
                          <th>Date</th>
                          <th>Reference</th>
                          <th>Amount</th>
                          <th>Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activePreview.candidates.map((candidate) => {
                          const transaction = candidate.bank_transaction;

                          return (
                            <tr key={transaction.id}>
                              <td>
                                <input
                                  type="radio"
                                  name={`candidate-${activePreview.statement_line_id}`}
                                  checked={
                                    selectedCandidates[
                                      activePreview.statement_line_id
                                    ] === transaction.id
                                  }
                                  onChange={() =>
                                    setSelectedCandidates((current) => ({
                                      ...current,
                                      [activePreview.statement_line_id]:
                                        transaction.id,
                                    }))
                                  }
                                />
                              </td>
                              <td>
                                #{transaction.id} — {transaction.description}
                              </td>
                              <td>{transaction.transaction_date}</td>
                              <td>{transaction.reference || "—"}</td>
                              <td>{formatPKR(transaction.amount)}</td>
                              <td>
                                <span
                                  className={`confidence-badge ${candidate.confidence}`}
                                >
                                  {candidate.confidence}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="match-reasons">
                    <strong>Matching reasons</strong>
                    <ul>
                      {activePreview.candidates
                        .find(
                          (candidate) =>
                            candidate.bank_transaction.id ===
                            selectedCandidates[activePreview.statement_line_id],
                        )
                        ?.match_reasons.map((reason, index) => (
                          <li key={index}>{reason}</li>
                        ))}
                    </ul>
                  </div>

                  <button
                    className="primary-button"
                    type="button"
                    onClick={() =>
                      void confirmMatch(activePreview.statement_line_id)
                    }
                    disabled={
                      matchingLineId === activePreview.statement_line_id ||
                      !selectedCandidates[activePreview.statement_line_id]
                    }
                  >
                    <Link2 size={16} />
                    {matchingLineId === activePreview.statement_line_id
                      ? "Confirming..."
                      : "Confirm selected match"}
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {/* Existing balance reconciliation */}
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
              setActivePreview(null);
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
              setActivePreview(null);
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

      {/* Existing reconciliation history */}
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
                    record.account_type === "bank"
                      ? bankAccounts
                      : cashAccounts;

                  const account = accountList.find(
                    (item) => item.id === record.account_id,
                  );

                  return (
                    <tr key={record.id}>
                      <td>#{record.id}</td>
                      <td>{record.account_type.toUpperCase()}</td>
                      <td>
                        {account?.name ?? `Account #${record.account_id}`}
                      </td>
                      <td>{record.statement_date}</td>
                      <td>
                        {formatPKR(record.statement_closing_balance)}
                      </td>
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
