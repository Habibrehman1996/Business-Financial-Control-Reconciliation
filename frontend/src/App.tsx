import ReconciliationPage from "./ReconciliationPage";
import JournalPage from "./JournalPage";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Banknote,
  Pencil,
  SlidersHorizontal,
  History,
  XCircle,
  Bell,
  Boxes,
  BriefcaseBusiness,
  ChevronRight,
  CircleHelp,
  FileBarChart,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Search,
  Settings,
  ShoppingCart,
  Wallet,
  X,
  BookOpen,
  ClipboardList,
  AlertCircle,
  Scale,
  
} from "lucide-react";
import { apiGet, apiPost, apiPut, asArray, formatPKR,  } from "./api";
import "./App.css";


type Section =
  | "Overview"
  | "Banking"
  | "Cash"
  | "Customers"
  | "Suppliers"
  | "Sales"
  | "Purchases"
  | "Inventory"
  | "Expenses"
  | "Journal"
  | "Reports"
  | "Reconciliation";
const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Banking", icon: Banknote, endpoint: "/api/bank/accounts" },
  { name: "Cash", icon: Wallet, endpoint: "/api/cash/accounts" },
  { name: "Customers", icon: BriefcaseBusiness, endpoint: "/api/parties/customers" },
  { name: "Suppliers", icon: ShoppingCart, endpoint: "/api/parties/suppliers" },
  { name: "Sales", icon: ArrowUpRight, endpoint: "/api/sales/invoices" },
  { name: "Purchases", icon: ArrowDownLeft, endpoint: "/api/purchases/bills" },
  { name: "Inventory", icon: Boxes, endpoint: "/api/inventory/products" },
  { name: "Expenses", icon: ClipboardList, endpoint: "/api/expenses" },
  { name: "Journal", icon: BookOpen, endpoint: "/api/journal" },
  { name: "Reconciliation", icon: Scale },
  { name: "Reports", icon: FileBarChart, endpoint: "/api/reports/trial-balance" },
] as const;

function StatCard({
  title,
  value,
  icon: Icon,
  color,
  description,
}: {
  title: string;
  value: string;
  icon: typeof Activity;
  color: string;
  description: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-heading">
        <span>{title}</span>
        <div className={`stat-icon ${color}`}>
          <Icon size={19} />
        </div>
      </div>
      <h2>{value}</h2>
      <p>{description}</p>
    </div>
  );
}

function RecordsTable({ rows }: { rows: any[] }) {
  if (!rows.length) {
    return <div className="empty-state">No records found yet.</div>;
  }

  const preferred = [
    "id",
    "name",
    "bank_name",
    "transaction_date",
    "description",
    "reference",
    "direction",
    "amount",
    "status",
    "is_active",
  ];

  const allKeys = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row ?? {}))),
  );

  const keys = [
    ...preferred.filter((key) => allKeys.includes(key)),
    ...allKeys.filter((key) => !preferred.includes(key)),
  ].slice(0, 7);

  const formatValue = (key: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return "—";

    if (typeof value === "boolean") {
      return value ? "Yes" : "No";
    }

    if (key === "amount" || key.includes("balance")) {
      return formatPKR(value);
    }

    return String(value);
  };

  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            {keys.map((key) => (
              <th key={key}>{key.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id ?? index}>
              {keys.map((key) => (
                <td key={key}>{formatValue(key, row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview({ onNavigate }: { onNavigate: (name: Section) => void }) {
  const [dashboard, setDashboard] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = async () => {
    setLoading(true);
    setError("");

    try {
      const [summary, bankTransactions] = await Promise.all([
        apiGet<any>("/api/reports/dashboard"),
        apiGet<any>("/api/bank/transactions").catch(() => []),
      ]);

      setDashboard(summary);
      setTransactions(asArray(bankTransactions).slice(0, 5));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load dashboard data.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const getAmount = (...keys: string[]) => {
    for (const key of keys) {
      const value = dashboard?.[key];
      if (value !== undefined && value !== null && Number.isFinite(Number(value))) {
        return Number(value);
      }
    }
    return 0;
  };

  const revenue = getAmount("revenue", "total_revenue", "sales");
  const expenses = getAmount("expenses", "total_expenses");
  const profit = getAmount("net_profit", "profit");
  const cash = getAmount("cash_balance", "cash");
  const bank = getAmount("bank_balance", "bank");

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">BUSINESS OVERVIEW</span>
          <h1>Business Dashboard</h1>
          <p>Monitor your business finances and daily operations.</p>
        </div>

        <button className="secondary-button" onClick={() => void loadDashboard()}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="error-message">
          <AlertCircle size={19} />
          <div>
            <strong>Dashboard data unavailable</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      <div className="stats-grid">
        <StatCard
          title="Total Revenue"
          value={loading ? "Loading..." : formatPKR(revenue)}
          icon={ArrowUpRight}
          color="green"
          description="Recorded business revenue"
        />
        <StatCard
          title="Total Expenses"
          value={loading ? "Loading..." : formatPKR(expenses)}
          icon={ArrowDownLeft}
          color="orange"
          description="Recorded business expenses"
        />
        <StatCard
          title="Net Profit"
          value={loading ? "Loading..." : formatPKR(profit)}
          icon={Activity}
          color="blue"
          description="Calculated from ledger records"
        />
        <StatCard
          title="Cash + Bank"
          value={loading ? "Loading..." : formatPKR(cash + bank)}
          icon={Wallet}
          color="purple"
          description="Recorded account balances"
        />
      </div>

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Financial Position</h2>
              <p>Current figures from your accounting backend</p>
            </div>
            <span className="live-status">● Live data</span>
          </div>

          {loading ? (
            <div className="empty-state">Loading financial position...</div>
          ) : (
            <div className="financial-list">
              <div><span>Cash Balance</span><strong>{formatPKR(cash)}</strong></div>
              <div><span>Bank Balance</span><strong>{formatPKR(bank)}</strong></div>
              <div><span>Total Revenue</span><strong>{formatPKR(revenue)}</strong></div>
              <div><span>Total Expenses</span><strong>{formatPKR(expenses)}</strong></div>
              <div className="profit-row"><span>Net Profit</span><strong>{formatPKR(profit)}</strong></div>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Quick Access</h2>
              <p>Open your business modules</p>
            </div>
          </div>

          <div className="quick-grid">
            {(["Banking", "Cash", "Customers", "Suppliers", "Inventory", "Reports"] as Section[]).map((name) => (
              <button key={name} onClick={() => onNavigate(name)} className="quick-item">
                <span>{name}</span>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </section>
      </div>

      <section className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <h2>Recent Bank Transactions</h2>
            <p>Latest transactions recorded in your system</p>
          </div>
          <button className="link-button" onClick={() => onNavigate("Banking")}>
            View all <ChevronRight size={15} />
          </button>
        </div>

        {loading ? (
          <div className="empty-state">Loading transactions...</div>
        ) : (
          <RecordsTable rows={transactions} />
        )}
      </section>
    </>
  );
}


function ModulePage({ section }: { section: Section }) {
  const item = navigation.find((entry) => entry.name === section);

  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState("");
  const [editProduct, setEditProduct] = useState<any>(null);
  const [adjustmentProduct, setAdjustmentProduct] = useState<any>(null);
  const [historyProduct, setHistoryProduct] = useState<any>(null);
  const [movementRows, setMovementRows] = useState<any[]>([]);
  const [salesCustomers, setSalesCustomers] = useState<any[]>([]);
  const [salesProducts, setSalesProducts] = useState<any[]>([]);
  const [invoiceForm, setInvoiceForm] = useState({
    invoice_number: "",
    customer_id: "",
    invoice_date: new Date().toISOString().slice(0, 10),
    due_date: "",
    tax_amount: "0",
    notes: "",
  });
  const [invoiceItems, setInvoiceItems] = useState<
    { product_id: string; quantity: string; unit_price: string }[]
  >([{ product_id: "", quantity: "1", unit_price: "0" }]);
    // Customer payment data
  const [salesPayments, setSalesPayments] = useState<any[]>([]);
  const [cashAccounts, setCashAccounts] = useState<any[]>([]);
  const [bankAccounts, setBankAccounts] = useState<any[]>([]);

  const [paymentForm, setPaymentForm] = useState({
    invoice_id: "",
    payment_date: new Date().toISOString().slice(0, 10),
    amount: "",
    payment_method: "cash",
    account_id: "",
    reference: "",
  });

  const [editForm, setEditForm] = useState({
    sku: "",
    name: "",
    description: "",
    unit: "piece",
    purchase_price: "",
    selling_price: "",
  });

  const [adjustmentForm, setAdjustmentForm] = useState({
    adjustment_date: new Date().toISOString().slice(0, 10),
    adjustment_type: "increase",
    quantity: "",
    reference: "",
    notes: "",
  });

  const [form, setForm] = useState({
    sku: "",
    name: "",
    description: "",
    unit: "piece",
    purchase_price: "",
    selling_price: "",
    opening_quantity: "0",
  });
  const [partyForm, setPartyForm] = useState({
    name: "",
    phone: "",
    email: "",
    address: "",
    opening_balance: "0",
  });
  const loadRecords = useCallback(async () => {
    if (!item || !("endpoint" in item)) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const result = await apiGet<any>(item.endpoint);
      setRows(asArray(result));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load records.");
    } finally {
      setLoading(false);
    }
  }, [item]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);
    useEffect(() => {
    if (section !== "Sales") return;

    async function loadSalesOptions() {
      try {
        const [
          customersResult,
          productsResult,
          paymentsResult,
          cashResult,
          bankResult,
        ] = await Promise.all([
          apiGet<any>("/api/parties/customers"),
          apiGet<any>("/api/inventory/products"),
          apiGet<any>("/api/sales/payments"),
          apiGet<any>("/api/cash/accounts"),
          apiGet<any>("/api/bank/accounts"),
        ]);

        setSalesCustomers(
          asArray(customersResult).filter(
            (customer: any) => customer.is_active !== false,
          ),
        );

        setSalesProducts(
          asArray(productsResult).filter(
            (product: any) => product.is_active !== false,
          ),
        );

        setSalesPayments(asArray(paymentsResult));
        setCashAccounts(asArray(cashResult));
        setBankAccounts(asArray(bankResult));
            } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load sales and payment information.",
        );
      }
    }

    void loadSalesOptions();
  }, [section]);
  async function createProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const purchasePrice = Number(form.purchase_price);
    const sellingPrice = Number(form.selling_price);
    const openingQuantity = Number(form.opening_quantity);

    if (
      !form.sku.trim() ||
      form.name.trim().length < 2 ||
      !Number.isFinite(purchasePrice) ||
      !Number.isFinite(sellingPrice) ||
      !Number.isFinite(openingQuantity) ||
      purchasePrice < 0 ||
      sellingPrice < 0 ||
      openingQuantity < 0
    ) {
      setError("Please enter valid product details and amounts.");
      return;
    }

    setSaving(true);

    try {
      await apiPost("/api/inventory/products", {
        sku: form.sku.trim(),
        name: form.name.trim(),
        description: form.description.trim() || null,
        unit: form.unit.trim() || "piece",
        purchase_price: purchasePrice,
        selling_price: sellingPrice,
        opening_quantity: openingQuantity,
      });

      setForm({
        sku: "",
        name: "",
        description: "",
        unit: "piece",
        purchase_price: "",
        selling_price: "",
        opening_quantity: "0",
      });

      setSuccess("Product created successfully.");
      await loadRecords();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create product.",
      );
    } finally {
      setSaving(false);
    }
  }
      function updateInvoiceItem(
    index: number,
    field: "product_id" | "quantity" | "unit_price",
    value: string,
  ) {
    setInvoiceItems((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  function addInvoiceItem() {
    setInvoiceItems((current) => [
      ...current,
      { product_id: "", quantity: "1", unit_price: "0" },
    ]);
  }

  function removeInvoiceItem(index: number) {
    setInvoiceItems((current) =>
      current.length > 1
        ? current.filter((_, itemIndex) => itemIndex !== index)
        : current,
    );
  }

  const invoiceSubtotal = invoiceItems.reduce((total, item) => {
    const quantity = Number(item.quantity);
    const price = Number(item.unit_price);

    return total +
      (Number.isFinite(quantity) && Number.isFinite(price)
        ? quantity * price
        : 0);
  }, 0);
  const getInvoicePaid = (invoiceId: number) =>
    salesPayments
      .filter((payment) => Number(payment.invoice_id) === invoiceId)
      .reduce((total, payment) => total + Number(payment.amount || 0), 0);

  const getInvoiceOutstanding = (invoice: any) =>
    Math.max(
      0,
      Number(invoice.total_amount || 0) - getInvoicePaid(Number(invoice.id)),
    );

  const outstandingInvoices = rows.filter(
    (invoice) =>
      invoice.status !== "cancelled" &&
      getInvoiceOutstanding(invoice) > 0,
  );

  const selectedPaymentInvoice = outstandingInvoices.find(
    (invoice) => Number(invoice.id) === Number(paymentForm.invoice_id),
  );

  const selectedPaymentAccounts =
    paymentForm.payment_method === "cash" ? cashAccounts : bankAccounts;
  const invoiceTax = Number(invoiceForm.tax_amount) || 0;
  const invoiceTotal = invoiceSubtotal + invoiceTax;
  async function recordCustomerPayment(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const invoiceId = Number(paymentForm.invoice_id);
    const amount = Number(paymentForm.amount);
    const accountId = Number(paymentForm.account_id);

    if (
      !Number.isInteger(invoiceId) ||
      invoiceId <= 0 ||
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isInteger(accountId) ||
      accountId <= 0
    ) {
      setError("Please select an invoice, account, and valid payment amount.");
      return;
    }

    const invoice = outstandingInvoices.find(
      (item) => Number(item.id) === invoiceId,
    );

    if (!invoice) {
      setError("Selected invoice has no outstanding balance.");
      return;
    }

    const outstanding = getInvoiceOutstanding(invoice);

    if (amount > outstanding) {
      setError(`Payment cannot exceed outstanding balance of ${formatPKR(outstanding)}.`);
      return;
    }

    const confirmed = window.confirm(
      `Record customer payment of ${formatPKR(amount)} for invoice ${invoice.invoice_number}?\n\nThis will post a journal entry and reduce Accounts Receivable. Continue?`,
    );

    if (!confirmed) return;

    setSaving(true);

    try {
      await apiPost("/api/sales/payments", {
        invoice_id: invoiceId,
        payment_date: paymentForm.payment_date,
        amount,
        payment_method: paymentForm.payment_method,
        bank_account_id:
          paymentForm.payment_method === "bank" ? accountId : null,
        cash_account_id:
          paymentForm.payment_method === "cash" ? accountId : null,
        reference: paymentForm.reference.trim() || null,
      });

      setPaymentForm({
        invoice_id: "",
        payment_date: new Date().toISOString().slice(0, 10),
        amount: "",
        payment_method: "cash",
        account_id: "",
        reference: "",
      });

      const [paymentsResult, invoicesResult] = await Promise.all([
        apiGet<any>("/api/sales/payments"),
        apiGet<any>("/api/sales/invoices"),
      ]);

      setSalesPayments(asArray(paymentsResult));
      setRows(asArray(invoicesResult));

      setSuccess("Customer payment recorded successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to record customer payment.",
      );
    } finally {
      setSaving(false);
    }
  }
  async function createSalesInvoice(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const taxAmount = Number(invoiceForm.tax_amount);
    const customerId = Number(invoiceForm.customer_id);

    if (
      !invoiceForm.invoice_number.trim() ||
      !Number.isInteger(customerId) ||
      !Number.isFinite(taxAmount) ||
      taxAmount < 0
    ) {
      setError("Please enter a valid invoice number, customer, and tax amount.");
      return;
    }

    const validItems = invoiceItems.map((item) => ({
      product_id: Number(item.product_id),
      quantity: Number(item.quantity),
      unit_price: Number(item.unit_price),
    }));

    if (
      validItems.some(
        (item) =>
          !Number.isInteger(item.product_id) ||
          item.product_id <= 0 ||
          !Number.isFinite(item.quantity) ||
          item.quantity <= 0 ||
          !Number.isFinite(item.unit_price) ||
          item.unit_price < 0,
      )
    ) {
      setError("Please select a product and enter valid quantities and prices.");
      return;
    }

    if (
      !window.confirm(
        `Create invoice ${invoiceForm.invoice_number.trim()} for ${formatPKR(invoiceTotal)}?\n\nThis will deduct inventory stock and post accounting journal entries. This action cannot be treated as a preview. Continue?`,
      )
    ) {
      return;
    }

    setSaving(true);

    try {
      await apiPost("/api/sales/invoices", {
        invoice_number: invoiceForm.invoice_number.trim(),
        customer_id: customerId,
        invoice_date: invoiceForm.invoice_date,
        due_date: invoiceForm.due_date || null,
        tax_amount: taxAmount,
        notes: invoiceForm.notes.trim() || null,
        items: validItems,
      });

      setInvoiceForm({
        invoice_number: "",
        customer_id: "",
        invoice_date: new Date().toISOString().slice(0, 10),
        due_date: "",
        tax_amount: "0",
        notes: "",
      });

      setInvoiceItems([
        { product_id: "", quantity: "1", unit_price: "0" },
      ]);

      setSuccess("Sales invoice created successfully. Stock and accounting records updated.");
      await loadRecords();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create sales invoice.",
      );
    } finally {
      setSaving(false);
    }
  }
    function openEditProduct(product: any) {
    setEditProduct(product);
    setEditForm({
      sku: product.sku ?? "",
      name: product.name ?? "",
      description: product.description ?? "",
      unit: product.unit ?? "piece",
      purchase_price: String(product.purchase_price ?? 0),
      selling_price: String(product.selling_price ?? 0),
    });
    setError("");
    setSuccess("");
  }

  async function createParty(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const name = partyForm.name.trim();
    const openingBalance = Number(partyForm.opening_balance);

    if (
      name.length < 2 ||
      !Number.isFinite(openingBalance)
    ) {
      setError("Please enter a valid name and opening balance.");
      return;
    }

    if (
      openingBalance !== 0 &&
      !window.confirm(
        `You are about to save an opening balance of ${formatPKR(openingBalance)}. This may create a journal entry. Continue?`,
      )
    ) {
      return;
    }

    const endpoint =
      section === "Customers"
        ? "/api/parties/customers"
        : "/api/parties/suppliers";

    setSaving(true);

    try {
      await apiPost(endpoint, {
        name,
        phone: partyForm.phone.trim() || null,
        email: partyForm.email.trim() || null,
        address: partyForm.address.trim() || null,
        opening_balance: openingBalance,
      });

      setPartyForm({
        name: "",
        phone: "",
        email: "",
        address: "",
        opening_balance: "0",
      });

      setSuccess(
        `${section === "Customers" ? "Customer" : "Supplier"} created successfully.`,
      );

      await loadRecords();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : `Unable to create ${section.toLowerCase().slice(0, -1)}.`,
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editProduct) return;

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      await apiPut(`/api/inventory/products/${editProduct.id}`, {
        sku: editForm.sku.trim(),
        name: editForm.name.trim(),
        description: editForm.description.trim() || null,
        unit: editForm.unit.trim(),
        purchase_price: Number(editForm.purchase_price),
        selling_price: Number(editForm.selling_price),
      });

      setEditProduct(null);
      setSuccess("Product updated successfully.");
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update product.");
    } finally {
      setSaving(false);
    }
  }

  async function adjustStock(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!adjustmentProduct) return;

    const quantity = Number(adjustmentForm.quantity);

    if (!Number.isFinite(quantity) || quantity <= 0) {
      setError("Please enter a valid stock quantity.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      await apiPost(
        `/api/inventory/products/${adjustmentProduct.id}/adjustments`,
        {
          ...adjustmentForm,
          quantity,
        },
      );

      setAdjustmentProduct(null);
      setAdjustmentForm({
        adjustment_date: new Date().toISOString().slice(0, 10),
        adjustment_type: "increase",
        quantity: "",
        reference: "",
        notes: "",
      });

      setSuccess("Stock adjusted successfully.");
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to adjust stock.");
    } finally {
      setSaving(false);
    }
  }

  async function openMovementHistory(product: any) {
    setHistoryProduct(product);
    setMovementRows([]);
    setError("");

    try {
      const result = await apiGet(
        `/api/inventory/products/${product.id}/movements`,
      );
      setMovementRows(asArray(result));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load stock history.",
      );
    }
  }
  const filteredRows = rows.filter((row) =>
    JSON.stringify(row).toLowerCase().includes(search.toLowerCase()),
  );

  const isInventory = section === "Inventory";
  const isSales = section === "Sales";
  const isParty = section === "Customers" || section === "Suppliers";
  const partyLabel = section === "Customers" ? "Customer" : "Supplier";

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">BUSINESS MODULE</span>
          <h1>{section}</h1>
          <p>Manage and review your business records.</p>
        </div>
      </div>
            {section === "Sales" && (
        <section className="panel inventory-create-panel sales-invoice-panel">
          <div className="panel-heading">
            <div>
              <h2>Create Sales Invoice</h2>
              <p>Create an invoice for a customer and record the products sold.</p>
            </div>
          </div>

          <form className="inventory-form" onSubmit={createSalesInvoice}>
            <div className="inventory-form-grid">
              <label>
                Invoice Number *
                <input
                  required
                  maxLength={40}
                  value={invoiceForm.invoice_number}
                  onChange={(event) =>
                    setInvoiceForm({
                      ...invoiceForm,
                      invoice_number: event.target.value,
                    })
                  }
                  placeholder="e.g. INV-2026-001"
                />
              </label>

              <label>
                Customer *
                <select
                  required
                  value={invoiceForm.customer_id}
                  onChange={(event) =>
                    setInvoiceForm({
                      ...invoiceForm,
                      customer_id: event.target.value,
                    })
                  }
                >
                  <option value="">Select customer</option>
                  {salesCustomers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Invoice Date *
                <input
                  type="date"
                  required
                  value={invoiceForm.invoice_date}
                  onChange={(event) =>
                    setInvoiceForm({
                      ...invoiceForm,
                      invoice_date: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Due Date
                <input
                  type="date"
                  value={invoiceForm.due_date}
                  min={invoiceForm.invoice_date}
                  onChange={(event) =>
                    setInvoiceForm({
                      ...invoiceForm,
                      due_date: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Tax Amount (PKR)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={invoiceForm.tax_amount}
                  onChange={(event) =>
                    setInvoiceForm({
                      ...invoiceForm,
                      tax_amount: event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <div className="panel-heading">
              <div>
                <h3>Invoice Items</h3>
                <p>Select products, quantities, and selling prices.</p>
              </div>

              <button type="button" onClick={addInvoiceItem}>
                Add Item
              </button>
            </div>

            {invoiceItems.map((item, index) => (
              <div
                className="inventory-form-grid sales-invoice-item-row"
                key={index}
              >
                <label>
                  Product *
                  <select
                    required
                    value={item.product_id}
                    onChange={(event) => {
                      const product = salesProducts.find(
                        (entry) => entry.id === Number(event.target.value),
                      );

                      updateInvoiceItem(
                        index,
                        "product_id",
                        event.target.value,
                      );

                      if (product) {
                        updateInvoiceItem(
                          index,
                          "unit_price",
                          String(product.selling_price ?? 0),
                        );
                      }
                    }}
                  >
                    <option value="">Select product</option>
                    {salesProducts.map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} — Stock:{" "}
                        {product.current_stock ?? product.quantity_on_hand ?? 0}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Quantity *
                  <input
                    type="number"
                    min="0.001"
                    step="0.001"
                    required
                    value={item.quantity}
                    onChange={(event) =>
                      updateInvoiceItem(index, "quantity", event.target.value)
                    }
                  />
                </label>

                <label>
                  Unit Price (PKR) *
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    value={item.unit_price}
                    onChange={(event) =>
                      updateInvoiceItem(index, "unit_price", event.target.value)
                    }
                  />
                </label>

                <div className="inventory-form-actions">
                  <button
                    type="button"
                    className="sales-remove-button"
                    disabled={invoiceItems.length === 1}
                    onClick={() => removeInvoiceItem(index)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}

            <label>
              Notes
              <textarea
                value={invoiceForm.notes}
                onChange={(event) =>
                  setInvoiceForm({
                    ...invoiceForm,
                    notes: event.target.value,
                  })
                }
                placeholder="Optional invoice notes..."
                rows={3}
              />
            </label>

            <div className="panel-heading">
              <div>
                <div className="sales-invoice-totals">
                <div>
                  <span>Subtotal</span>
                  <strong>{formatPKR(invoiceSubtotal)}</strong>
                </div>
                <div>
                  <span>Tax</span>
                  <strong>{formatPKR(invoiceTax)}</strong>
                </div>
                <div className="sales-invoice-grand-total">
                  <span>Grand Total</span>
                  <strong>{formatPKR(invoiceTotal)}</strong>
                </div>
              </div>
              </div>
            </div>

            <div className="inventory-form-actions">
              <button type="submit" disabled={saving}>
                {saving ? "Creating Invoice..." : "Create Sales Invoice"}
              </button>
            </div>
          </form>
        </section>
      )}
            {isSales && (
        <section className="panel inventory-create-panel">
          <div className="panel-heading">
            <div>
              <h2>Record Customer Payment</h2>
              <p>Record cash or bank payments against outstanding sales invoices.</p>
            </div>
          </div>

          <form className="inventory-form" onSubmit={recordCustomerPayment}>
            <div className="inventory-form-grid">
              <label>
                Sales Invoice *
                <select
                  required
                  value={paymentForm.invoice_id}
                  onChange={(event) => {
                    setPaymentForm({
                      ...paymentForm,
                      invoice_id: event.target.value,
                      amount: "",
                    });
                  }}
                >
                  <option value="">Select outstanding invoice</option>
                  {outstandingInvoices.map((invoice) => {
                    const customer = salesCustomers.find(
                      (item) => Number(item.id) === Number(invoice.customer_id),
                    );

                    return (
                      <option key={invoice.id} value={invoice.id}>
                        {invoice.invoice_number} — {customer?.name ?? "Customer"} — Outstanding: {formatPKR(getInvoiceOutstanding(invoice))}
                      </option>
                    );
                  })}
                </select>
              </label>

              <label>
                Payment Date *
                <input
                  type="date"
                  required
                  value={paymentForm.payment_date}
                  onChange={(event) =>
                    setPaymentForm({ ...paymentForm, payment_date: event.target.value })
                  }
                />
              </label>

              <label>
                Payment Amount (PKR) *
                <input
                  type="number"
                  required
                  min="0.01"
                  step="0.01"
                  max={selectedPaymentInvoice ? getInvoiceOutstanding(selectedPaymentInvoice) : undefined}
                  value={paymentForm.amount}
                  onChange={(event) =>
                    setPaymentForm({ ...paymentForm, amount: event.target.value })
                  }
                  placeholder="Enter payment amount"
                />
              </label>

              <label>
                Payment Method *
                <select
                  value={paymentForm.payment_method}
                  onChange={(event) =>
                    setPaymentForm({
                      ...paymentForm,
                      payment_method: event.target.value,
                      account_id: "",
                    })
                  }
                >
                  <option value="cash">Cash</option>
                  <option value="bank">Bank</option>
                </select>
              </label>

              <label>
                {paymentForm.payment_method === "cash" ? "Cash Account *" : "Bank Account *"}
                <select
                  required
                  value={paymentForm.account_id}
                  onChange={(event) =>
                    setPaymentForm({ ...paymentForm, account_id: event.target.value })
                  }
                >
                  <option value="">Select account</option>
                  {selectedPaymentAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {paymentForm.payment_method === "cash"
                        ? account.name
                        : `${account.name} — ${account.bank_name} (${account.account_number})`}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Reference (Optional)
                <input
                  maxLength={100}
                  value={paymentForm.reference}
                  onChange={(event) =>
                    setPaymentForm({ ...paymentForm, reference: event.target.value })
                  }
                  placeholder="Receipt or transaction reference"
                />
              </label>
            </div>

            {selectedPaymentInvoice && (
              <p>
                Outstanding balance: <strong>{formatPKR(getInvoiceOutstanding(selectedPaymentInvoice))}</strong>
              </p>
            )}

            {outstandingInvoices.length === 0 && (
              <p className="empty-state">
                No outstanding sales invoices available for payment.
              </p>
            )}

            <div className="inventory-form-actions">
              <button
                type="submit"
                disabled={saving || outstandingInvoices.length === 0}
              >
                {saving ? "Recording Payment..." : "Record Customer Payment"}
              </button>
            </div>
          </form>
        </section>
      )}
          {isParty && (
        <section className="panel inventory-create-panel">
          <div className="panel-heading">
            <div>
              <h2>Add New {partyLabel}</h2>
              <p>Enter contact details and an optional opening balance.</p>
            </div>
          </div>

          <form className="inventory-form" onSubmit={createParty}>
            <div className="inventory-form-grid">
              <label>
                {partyLabel} Name *
                <input
                  required
                  minLength={2}
                  maxLength={150}
                  value={partyForm.name}
                  onChange={(e) =>
                    setPartyForm({ ...partyForm, name: e.target.value })
                  }
                  placeholder={`Enter ${partyLabel.toLowerCase()} name`}
                />
              </label>

              <label>
                Phone
                <input
                  type="tel"
                  value={partyForm.phone}
                  onChange={(e) =>
                    setPartyForm({ ...partyForm, phone: e.target.value })
                  }
                  placeholder="Optional phone number"
                />
              </label>

              <label>
                Email
                <input
                  type="email"
                  value={partyForm.email}
                  onChange={(e) =>
                    setPartyForm({ ...partyForm, email: e.target.value })
                  }
                  placeholder="Optional email address"
                />
              </label>

              <label>
                Opening Balance (PKR)
                <input
                  type="number"
                  step="0.01"
                  value={partyForm.opening_balance}
                  onChange={(e) =>
                    setPartyForm({
                      ...partyForm,
                      opening_balance: e.target.value,
                    })
                  }
                  placeholder="0"
                />
              </label>

              <label className="inventory-description">
                Address
                <textarea
                  rows={3}
                  value={partyForm.address}
                  onChange={(e) =>
                    setPartyForm({ ...partyForm, address: e.target.value })
                  }
                  placeholder="Optional address"
                />
              </label>
            </div>

            <div className="inventory-form-actions">
              <button type="submit" disabled={saving}>
                {saving ? "Saving..." : `Add ${partyLabel}`}
              </button>
            </div>
          </form>
        </section>
      )}
      {isInventory && (
        <section className="panel inventory-create-panel">
          <div className="panel-heading">
            <div>
              <h2>Add New Product</h2>
              <p>Create a product and record its opening stock.</p>
            </div>
          </div>

          <form className="inventory-form" onSubmit={createProduct}>
            <div className="inventory-form-grid">
              <label>
                Product Name *
                <input
                  required
                  minLength={2}
                  value={form.name}
                  onChange={(e) =>
                    setForm({ ...form, name: e.target.value })
                  }
                  placeholder="e.g. Laptop"
                />
              </label>

              <label>
                SKU / Product Code *
                <input
                  required
                  value={form.sku}
                  onChange={(e) =>
                    setForm({ ...form, sku: e.target.value })
                  }
                  placeholder="e.g. LAP-001"
                />
              </label>

              <label>
                Unit
                <input
                  value={form.unit}
                  onChange={(e) =>
                    setForm({ ...form, unit: e.target.value })
                  }
                  placeholder="piece"
                />
              </label>

              <label>
                Purchase Price (PKR) *
                <input
                  required
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.purchase_price}
                  onChange={(e) =>
                    setForm({ ...form, purchase_price: e.target.value })
                  }
                  placeholder="60000"
                />
              </label>

              <label>
                Selling Price (PKR) *
                <input
                  required
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.selling_price}
                  onChange={(e) =>
                    setForm({ ...form, selling_price: e.target.value })
                  }
                  placeholder="100000"
                />
              </label>

              <label>
                Opening Stock *
                <input
                  required
                  type="number"
                  min="0"
                  step="0.001"
                  value={form.opening_quantity}
                  onChange={(e) =>
                    setForm({ ...form, opening_quantity: e.target.value })
                  }
                />
              </label>

              <label className="inventory-description">
                Description
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                  placeholder="Optional product details..."
                  rows={3}
                />
              </label>
            </div>

            <div className="inventory-form-actions">
              <button type="submit" disabled={saving}>
                {saving ? "Saving Product..." : "Add Product"}
              </button>
            </div>

            {success && <p className="inventory-success">{success}</p>}
            {error && (
              <div className="error-message">
                <AlertCircle size={18} />
                <p>{error}</p>
              </div>
            )}
          </form>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading module-heading">
          <div>
            <h2>{section} Records</h2>
            <p>{rows.length} records available</p>
          </div>

          <label className="search-input">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search records..."
            />
          </label>
        </div>

                {loading ? (
          <div className="empty-state">Loading records...</div>
        ) : error && rows.length === 0 ? (
          <div className="error-message">
            <AlertCircle size={18} />
            <p>{error}</p>
          </div>
        ) : isInventory ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>SKU</th>
                  <th>Purchase Price</th>
                  <th>Selling Price</th>
                  <th>Current Stock</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((product) => (
                  <tr key={product.id}>
                    <td>{product.name}</td>
                    <td>{product.sku}</td>
                    <td>{formatPKR(product.purchase_price)}</td>
                    <td>{formatPKR(product.selling_price)}</td>
                    <td>{product.current_stock ?? product.quantity_on_hand ?? 0}</td>
                    <td>
                      <div className="inventory-form-actions">
                        <button
                          type="button"
                          onClick={() => openEditProduct(product)}
                          title="Edit product"
                        >
                          <Pencil size={15} /> Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => setAdjustmentProduct(product)}
                          title="Adjust stock"
                        >
                          <SlidersHorizontal size={15} /> Adjust
                        </button>
                        <button
                          type="button"
                          onClick={() => void openMovementHistory(product)}
                          title="Movement history"
                        >
                          <History size={15} /> History
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredRows.length === 0 && (
              <div className="empty-state">No products found.</div>
            )}
          </div>
        
        ) : isSales ? (
          <>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Invoice Number</th>
                  <th>Customer</th>
                  <th>Invoice Date</th>
                  <th>Due Date</th>
                  <th>Subtotal</th>
                  <th>Tax</th>
                  <th>Grand Total</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((invoice) => {
                  const customer = salesCustomers.find(
                    (item) => Number(item.id) === Number(invoice.customer_id),
                  );

                  return (
                    <tr key={invoice.id}>
                      <td>{invoice.invoice_number}</td>
                      <td>
                        {customer?.name ??
                          invoice.customer?.name ??
                          `Customer #${invoice.customer_id}`}
                      </td>
                      <td>{invoice.invoice_date ?? "—"}</td>
                      <td>{invoice.due_date ?? "—"}</td>
                      <td>{formatPKR(invoice.subtotal ?? 0)}</td>
                      <td>{formatPKR(invoice.tax_amount ?? 0)}</td>
                      <td>{formatPKR(invoice.total_amount ?? 0)}</td>
                      <td>
                        <span className={`status-badge status-${String(invoice.status ?? "unknown").toLowerCase()}`}>
                          {invoice.status ?? "Unknown"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            
            {filteredRows.length === 0 && (
              <div className="empty-state">
                No sales invoices found. Create your first invoice using the form above.
              </div>
            )}
          </div>

          <section className="panel inventory-create-panel">
            <div className="panel-heading">
              <div>
                <h2>Customer Payment History</h2>
                <p>View payments received against sales invoices.</p>
              </div>
            </div>

            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Payment Date</th>
                    <th>Invoice Number</th>
                    <th>Customer</th>
                    <th>Method</th>
                    <th>Account</th>
                    <th>Reference</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {salesPayments.map((payment) => {
                    const invoice = rows.find(
                      (item) => Number(item.id) === Number(payment.invoice_id),
                    );

                    const customer = salesCustomers.find(
                      (item) =>
                        Number(item.id) === Number(invoice?.customer_id),
                    );

                    const account =
                      payment.payment_method === "cash"
                        ? cashAccounts.find(
                            (item) =>
                              Number(item.id) === Number(payment.cash_account_id),
                          )
                        : bankAccounts.find(
                            (item) =>
                              Number(item.id) === Number(payment.bank_account_id),
                          );

                    return (
                      <tr key={payment.id}>
                        <td>{payment.payment_date ?? "—"}</td>
                        <td>
                          {invoice?.invoice_number ??
                            `Invoice #${payment.invoice_id}`}
                        </td>
                        <td>{customer?.name ?? "—"}</td>
                        <td>
                          {payment.payment_method === "cash" ? "Cash" : "Bank"}
                        </td>
                        <td>{account?.name ?? "—"}</td>
                        <td>{payment.reference ?? "—"}</td>
                        <td>{formatPKR(payment.amount ?? 0)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {salesPayments.length === 0 && (
                <div className="empty-state">
                  No customer payments recorded yet.
                </div>
              )}
            </div>
          </section>
          </>
        ) : (

          <RecordsTable rows={filteredRows} />
        )}


        {isInventory && editProduct && (
          <section className="panel inventory-create-panel">
            <div className="panel-heading">
              <div>
                <h2>Edit Product</h2>
                <p>Update product information. Current stock will remain unchanged.</p>
              </div>
              <button type="button" onClick={() => setEditProduct(null)}>
                <XCircle size={18} /> Close
              </button>
            </div>

            <form className="inventory-form" onSubmit={saveProduct}>
              <div className="inventory-form-grid">
                <label>
                  Product Name *
                  <input
                    required
                    minLength={2}
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  />
                </label>
                <label>
                  SKU *
                  <input
                    required
                    value={editForm.sku}
                    onChange={(e) => setEditForm({ ...editForm, sku: e.target.value })}
                  />
                </label>
                <label>
                  Unit
                  <input
                    value={editForm.unit}
                    onChange={(e) => setEditForm({ ...editForm, unit: e.target.value })}
                  />
                </label>
                <label>
                  Purchase Price (PKR) *
                  <input
                    required
                    type="number"
                    min="0"
                    step="0.01"
                    value={editForm.purchase_price}
                    onChange={(e) => setEditForm({ ...editForm, purchase_price: e.target.value })}
                  />
                </label>
                <label>
                  Selling Price (PKR) *
                  <input
                    required
                    type="number"
                    min="0"
                    step="0.01"
                    value={editForm.selling_price}
                    onChange={(e) => setEditForm({ ...editForm, selling_price: e.target.value })}
                  />
                </label>
                <label className="inventory-description">
                  Description
                  <textarea
                    rows={3}
                    value={editForm.description}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  />
                </label>
              </div>
              <div className="inventory-form-actions">
                <button type="submit" disabled={saving}>
                  {saving ? "Updating..." : "Save Changes"}
                </button>
              </div>
            </form>
          </section>
        )}

        {isInventory && adjustmentProduct && (
          <section className="panel inventory-create-panel">
            <div className="panel-heading">
              <div>
                <h2>Stock Adjustment</h2>
                <p>
                  {adjustmentProduct.name} — Current stock:{" "}
                  {adjustmentProduct.current_stock ?? adjustmentProduct.quantity_on_hand ?? 0}
                </p>
              </div>
              <button type="button" onClick={() => setAdjustmentProduct(null)}>
                <XCircle size={18} /> Close
              </button>
            </div>

            <form className="inventory-form" onSubmit={adjustStock}>
              <div className="inventory-form-grid">
                <label>
                  Adjustment Date *
                  <input
                    required
                    type="date"
                    value={adjustmentForm.adjustment_date}
                    onChange={(e) => setAdjustmentForm({ ...adjustmentForm, adjustment_date: e.target.value })}
                  />
                </label>
                <label>
                  Adjustment Type *
                  <select
                    value={adjustmentForm.adjustment_type}
                    onChange={(e) => setAdjustmentForm({ ...adjustmentForm, adjustment_type: e.target.value })}
                  >
                    <option value="increase">Increase Stock</option>
                    <option value="decrease">Decrease Stock</option>
                  </select>
                </label>
                <label>
                  Quantity *
                  <input
                    required
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={adjustmentForm.quantity}
                    onChange={(e) => setAdjustmentForm({ ...adjustmentForm, quantity: e.target.value })}
                  />
                </label>
                <label>
                  Reference
                  <input
                    value={adjustmentForm.reference}
                    onChange={(e) => setAdjustmentForm({ ...adjustmentForm, reference: e.target.value })}
                    placeholder="Optional reference"
                  />
                </label>
                <label className="inventory-description">
                  Notes
                  <textarea
                    rows={3}
                    value={adjustmentForm.notes}
                    onChange={(e) => setAdjustmentForm({ ...adjustmentForm, notes: e.target.value })}
                    placeholder="Reason for stock adjustment"
                  />
                </label>
              </div>
              <div className="inventory-form-actions">
                <button type="submit" disabled={saving}>
                  {saving ? "Processing..." : "Save Stock Adjustment"}
                </button>
              </div>
            </form>
          </section>
        )}

        {isInventory && historyProduct && (
          <section className="panel inventory-create-panel">
            <div className="panel-heading">
              <div>
                <h2>Stock Movement History</h2>
                <p>{historyProduct.name} — SKU: {historyProduct.sku}</p>
              </div>
              <button type="button" onClick={() => setHistoryProduct(null)}>
                <XCircle size={18} /> Close
              </button>
            </div>
            {movementRows.length > 0 ? (
              <RecordsTable rows={movementRows} />
            ) : (
              <div className="empty-state">No stock movements found.</div>
            )}
          </section>
        )}

        {success && <p className="inventory-success">{success}</p>}
        {error && (
          <div className="error-message">
            <AlertCircle size={18} />
            <p>{error}</p>
          </div>
        )}

        <div className="endpoint-note">
          API: <code>{item && "endpoint" in item ? item.endpoint : "Not configured"}</code>
        </div>
      </section>

      {!isInventory && !isParty && (
        <div className="info-note">
          <CircleHelp size={17} />
          This screen currently displays records from your backend. Create and edit forms
          will be connected after confirming each API's input schema.
        </div>
      )}
    </>
  );
}


export default function App() {
  const [active, setActive] = useState<Section>("Overview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    apiGet("/api/v1/health/ready")
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, []);

  const navigate = (section: Section) => {
    setActive(section);
    setMenuOpen(false);
  };

  return (
    <div className="app-shell">
      {menuOpen && (
        <button className="sidebar-overlay" onClick={() => setMenuOpen(false)} aria-label="Close menu" />
      )}

      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><Activity size={22} /></div>
          <div>
            <strong>FinControl</strong>
            <span>BUSINESS FINANCE</span>
          </div>
          <button className="close-menu" onClick={() => setMenuOpen(false)}><X size={19} /></button>
        </div>

        <div className="workspace-card">
          <div className="workspace-avatar">FC</div>
          <div><strong>Business Workspace</strong><span>Financial operations</span></div>
        </div>

        <span className="nav-heading">WORKSPACE</span>

        <nav className="navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={`nav-link ${active === name ? "selected" : ""}`}
              onClick={() => navigate(name as Section)}
            >
              <Icon size={18} />
              <span>{name}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card">
            <CircleHelp size={19} />
            <div><strong>Need help?</strong><span>Financial workflow support</span></div>
          </div>
          <button className="nav-link settings-link"><Settings size={18} /><span>Settings</span></button>
          <div className="user-profile">
            <div className="user-avatar">HR</div>
            <div><strong>Administrator</strong><span>Business account</span></div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setMenuOpen(true)}><Menu size={21} /></button>
            <div className="breadcrumb">Workspace <span>/</span> <strong>{active}</strong></div>
          </div>
          <div className="topbar-right">
            <div className={`api-status ${apiStatus}`}>
              <i />
              {apiStatus === "checking" ? "Checking API" : apiStatus === "online" ? "API Connected" : "API Offline"}
            </div>
            <button className="notification-button" title="Notifications"><Bell size={18} /></button>
            <div className="user-avatar top-avatar">HR</div>
          </div>
        </header>

        <div className="page-content">
          {active === "Overview" ? (
            <Overview onNavigate={navigate} />
          ) : active === "Journal" ? (
            <JournalPage />
          ) : active === "Reconciliation" ? (
            <ReconciliationPage />
          ) : (
            <ModulePage section={active} />
          )}
        </div>

        <footer className="footer">
          <span>© 2026 FinControl</span>
          <span>Business Accounting Platform · <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">API Documentation ↗</a></span>
        </footer>
      </main>
    </div>
  );
}

