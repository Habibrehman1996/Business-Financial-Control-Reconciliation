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
} from "lucide-react";
import { apiGet, apiPost, apiPut, asArray, formatPKR } from "./api";
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
  | "Reports";

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

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">BUSINESS MODULE</span>
          <h1>{section}</h1>
          <p>Manage and review your business records.</p>
        </div>
      </div>

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

      {!isInventory && (
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

