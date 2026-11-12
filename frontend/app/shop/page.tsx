"use client";

import Link from "next/link";
import { PayPalButtons, PayPalScriptProvider } from "@paypal/react-paypal-js";
import { AlertTriangle, ChevronDown, ChevronUp, CreditCard, LoaderCircle, LockKeyhole, Minus, Plus, ShieldCheck, ShoppingBag, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ActionBadge, AgentScoreBar, Card, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { Action, CheckoutDecisionResponse, CheckoutDemoOverride, CheckoutStatus, PaymentStatus } from "@/lib/types";

const products = [
  { id: "field-notebook", name: "Field notebook", detail: "Recycled paper, stitched binding", price: 18 },
  { id: "signal-mug", name: "Signal mug", detail: "Stoneware, midnight blue", price: 24 },
  { id: "desk-lamp", name: "Desk lamp", detail: "Warm brass, adjustable shade", price: 72 },
  { id: "travel-tote", name: "Travel tote", detail: "Heavy canvas, internal pocket", price: 46 },
];
const presets: { label: string; value: CheckoutDemoOverride | undefined }[] = [
  { label: "Normal daytime", value: undefined },
  { label: "2 AM purchase", value: { event_time: "2026-01-15T02:00:00Z" } },
  { label: "Foreign country", value: { country: "GB" } },
  { label: "High amount", value: { amount_multiplier: 10 } },
];
const actionForStatus: Record<PaymentStatus, Action> = { CREATED: "ALLOW", AUTHORIZED: "ALLOW", PENDING_2FA: "REQUEST_2FA", PENDING_REVIEW: "HOLD_FOR_REVIEW", CAPTURED: "ALLOW", VOIDED: "BLOCK", FAILED: "BLOCK" };
const statusLabel: Record<PaymentStatus, string> = { CREATED: "Payment created", AUTHORIZED: "Authorized", PENDING_2FA: "Verification required", PENDING_REVIEW: "Held for review", CAPTURED: "Captured", VOIDED: "Voided", FAILED: "Payment failed" };

const money = (value: number) => `$${value.toFixed(2)}`;

export default function ShopPage() {
  const clientId = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID;
  const devMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";
  const [cart, setCart] = useState<Record<string, number>>({});
  const [preset, setPreset] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [orderId, setOrderId] = useState("");
  const [txnId, setTxnId] = useState<number | null>(null);
  const [decision, setDecision] = useState<CheckoutDecisionResponse | null>(null);
  const [status, setStatus] = useState<CheckoutStatus | null>(null);
  const [otp, setOtp] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);

  const total = useMemo(() => products.reduce((sum, product) => sum + product.price * (cart[product.id] ?? 0), 0), [cart]);
  const itemCount = Object.values(cart).reduce((sum, quantity) => sum + quantity, 0);
  const needs2FA = decision?.decision === "REQUEST_2FA" && status?.payment_status === "PENDING_2FA";

  useEffect(() => {
    if (!orderId || !needs2FA) return;
    let active = true;
    const poll = () => api.checkoutStatus(orderId).then(value => active && setStatus(value)).catch(() => undefined);
    poll();
    const timer = window.setInterval(poll, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [needs2FA, orderId]);

  const changeQuantity = (id: string, delta: number) => {
    setCart(current => {
      const next = Math.max(0, (current[id] ?? 0) + delta);
      return { ...current, [id]: next };
    });
    setError("");
  };

  const createOrder = async () => {
    if (busy) throw new Error("Payment is already starting");
    if (total <= 0) throw new Error("Add an item before checking out");
    setBusy(true);
    setError("");
    setNotice("");
    setDecision(null);
    setStatus(null);
    const demo = devMode ? presets[preset].value : undefined;
    try {
      const response = await api.createCheckoutOrder(total, "FinSight demo store purchase", demo);
      setOrderId(response.order_id);
      return response.order_id;
    } catch (reason) {
      setBusy(false);
      setError(reason instanceof Error ? reason.message : "Could not create the PayPal order.");
      throw reason;
    }
  };

  const authorize = async (paypalOrderId: string) => {
    setError("");
    try {
      const response = await api.authorizeCheckout(paypalOrderId);
      setDecision(response);
      setTxnId(response.txn_id);
      setStatus(await api.checkoutStatus(paypalOrderId));
      setNotice(response.payment_status === "PENDING_2FA" ? "Verification is required before capture." : "Risk decision received.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authorization failed.");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    if (!txnId || otp.length !== 6 || otpBusy) return;
    setOtpBusy(true);
    setError("");
    try {
      await api.verify2FA(txnId, otp);
      if (orderId) setStatus(await api.checkoutStatus(orderId));
      setNotice("Verification submitted. Checking final payment status.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Verification failed.");
    } finally {
      setOtpBusy(false);
    }
  };

  const handleCancel = () => {
    setBusy(false);
    setNotice("PayPal checkout was cancelled. Your cart is unchanged.");
  };

  const simulated = devMode && Boolean(presets[preset].value);

  return <main className="shop-page shell">
    <header className="topbar"><Link href="/story" className="brand"><span className="brand-mark"><ShieldCheck size={19} /></span><span>FinSight <small>risk intelligence</small></span></Link><nav><Link href="/story">Story</Link><Link href="/live">Live</Link><Link href="/demo">Demo</Link><Link className="active" href="/shop">Shop</Link></nav><span className="shop-secure"><LockKeyhole size={13} /> Sandbox checkout</span></header>
    <section className="shop-hero"><div><span className="eyebrow">PAYPAL SHIELD AI / SANDBOX</span><h1>Buy something. Watch the decision.</h1><p>A real PayPal Sandbox authorization passes through the deterministic risk engine before money can be captured.</p></div><div className="shop-mark"><ShoppingBag size={26} /><span>USD<br />PAYMENTS</span></div></section>
    {error && <div className="shop-alert error" role="alert"><AlertTriangle size={16} />{error}<button onClick={() => setError("")} aria-label="Dismiss error" title="Dismiss error"><X size={15} /></button></div>}
    {notice && <div className="shop-alert" role="status">{notice}</div>}
    <div className="shop-layout">
      <section><div className="shop-section-head"><div><span className="eyebrow">DEMO STORE</span><h2>Objects for the desk</h2></div><span className="section-detail">{itemCount} item{itemCount === 1 ? "" : "s"}</span></div><div className="product-grid">{products.map(product => <Card className="product-card" key={product.id}><div className="product-art"><ShoppingBag size={22} /></div><div><h3>{product.name}</h3><p>{product.detail}</p></div><strong>{money(product.price)}</strong><div className="quantity"><button onClick={() => changeQuantity(product.id, -1)} disabled={!cart[product.id]} aria-label={`Remove one ${product.name}`} title="Remove one"><Minus size={14} /></button><span>{cart[product.id] ?? 0}</span><button onClick={() => changeQuantity(product.id, 1)} aria-label={`Add one ${product.name}`} title="Add one"><Plus size={14} /></button></div></Card>)}</div></section>
      <aside className="shop-checkout"><Card><SectionTitle eyebrow="YOUR ORDER" title="Ready to check out" detail={`${itemCount} item${itemCount === 1 ? "" : "s"}`} />{itemCount ? <div className="cart-lines">{products.filter(product => cart[product.id]).map(product => <div className="cart-line" key={product.id}><span>{product.name} × {cart[product.id]}</span><strong>{money(product.price * cart[product.id])}</strong></div>)}</div> : <p className="shop-muted">Choose an object to begin.</p>}<div className="cart-total"><span>Total</span><strong>{money(total)}</strong></div>{clientId && total > 0 ? <PayPalScriptProvider options={{ clientId, currency: "USD", intent: "authorize" }}><PayPalButtons style={{ layout: "vertical", shape: "rect", label: "paypal" }} disabled={busy} forceReRender={[total, preset]} createOrder={createOrder} onApprove={data => authorize(data.orderID)} onCancel={handleCancel} onError={reason => { setBusy(false); setError(reason instanceof Error ? reason.message : "PayPal could not open."); }} /></PayPalScriptProvider> : <div className="paypal-missing">{clientId ? "Add an item to enable PayPal." : "NEXT_PUBLIC_PAYPAL_CLIENT_ID is not configured."}</div>}<p className="checkout-note"><LockKeyhole size={13} /> Sandbox only. The risk engine decides before capture.</p></Card></aside>
    </div>
    {devMode && <section className="simulation-wrap"><button className="simulation-toggle" onClick={() => setDrawerOpen(value => !value)} aria-expanded={drawerOpen}><span><span className="simulated-dot" />Demo controls (simulation)</span>{drawerOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button>{drawerOpen && <div className="simulation-drawer"><p>Choose an input preset for the next order. The result is labelled simulated.</p><div className="preset-grid">{presets.map((item, index) => <button key={item.label} className={preset === index ? "selected" : ""} onClick={() => setPreset(index)} disabled={busy}>{item.label}</button>)}</div></div>}</section>}
    {(decision || status) && <ResultPanel decision={decision} status={status} simulated={simulated} />}
    {needs2FA && <Card className="shop-2fa"><SectionTitle eyebrow="VERIFICATION" title="Confirm this payment" detail="Capture waits for a successful verification" /><p>Enter the six-digit code from the verification channel. Biometric verification is not configured in this build.</p><div className="shop-otp"><input value={otp} onChange={event => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" maxLength={6} placeholder="000000" aria-label="Six-digit verification code" /><button className="button" onClick={verify} disabled={otp.length !== 6 || otpBusy}>{otpBusy ? <LoaderCircle size={14} className="spin" /> : <CreditCard size={14} />} {otpBusy ? "Checking" : "Verify payment"}</button></div></Card>}
    <footer><span>FinSight / PayPal Sandbox store</span><span>Capture is policy-gated</span></footer>
  </main>;
}

function ResultPanel({ decision, status, simulated }: { decision: CheckoutDecisionResponse | null; status: CheckoutStatus | null; simulated: boolean }) {
  const paymentStatus = status?.payment_status ?? decision?.payment_status ?? "CREATED";
  const action = decision?.decision ?? actionForStatus[paymentStatus];
  return <section className="shop-result"><div className="result-head"><div><span className="eyebrow">RISK ENGINE RESULT</span><h2>Payment decision</h2></div>{simulated && <span className="simulated-label">Simulated</span>}</div><div className="result-status"><ActionBadge action={action} /><strong>{statusLabel[paymentStatus]}</strong><span>{status?.paypal_order_id ? `Order ${status.paypal_order_id}` : "Awaiting status"}</span></div>{decision && <div className="result-grid"><div><SectionTitle eyebrow="THREE AGENTS" title="Signals" />{(["frequency", "time", "geo"] as const).map(agent => <div key={agent}><AgentScoreBar agent={agent} score={decision.scores[agent] ?? 0} /><ul className="shop-reasons">{decision.reasons.slice(0, 2).map(reason => <li key={`${agent}-${reason}`}>{reason}</li>)}</ul></div>)}</div><div className="policy-box"><span className="eyebrow">POLICY ACTION</span><ActionBadge action={decision.decision} /><p>{decision.decision === "ALLOW" ? "The order passed deterministic policy and was captured." : decision.decision === "REQUEST_2FA" ? "The authorization is held until verification succeeds." : decision.decision === "HOLD_FOR_REVIEW" ? "An analyst must review this payment before it can continue." : "The authorization was voided by policy."}</p><small>{decision.methods.join(" · ")}</small></div></div>}</section>;
}
