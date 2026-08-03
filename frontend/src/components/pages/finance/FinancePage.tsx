import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import {
  Coins,
  CreditCard,
  History,
  ChevronLeft,
  Plus,
  QrCode,
  Loader2,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { API, type FinanceTransaction } from "@/api";

interface TransactionListResponse {
  transactions: FinanceTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export function FinancePage() {
  const [, setLocation] = useLocation();
  const [loading, setLoading] = useState(true);
  const [transactions, setTransactions] = useState<FinanceTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [credits, setCredits] = useState(0);
  const [showRecharge, setShowRecharge] = useState(false);
  // 弹窗关闭后,触发交易记录重新拉取(确保充值到账后立刻显示)
  const [txRefreshTick, setTxRefreshTick] = useState(0);
  const [rechargeAmount, setRechargeAmount] = useState("");
  const [recharging, setRecharging] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null);

  // 积分轮询,保持实时更新
  const [initialCredits, setInitialCredits] = useState(0);
  useEffect(() => {
    function fetchCredits() {
      API.getCredits()
        .then((res) => {
          setCredits(res.credits);
          // 如果充值后积分增加,自动关闭弹窗
          if (qrCodeUrl && initialCredits > 0 && res.credits > initialCredits) {
            setQrCodeUrl(null);
            setRechargeAmount("");
            setShowRecharge(false);
            setTxRefreshTick((x) => x + 1);  // 触发交易记录刷新
            setInitialCredits(0);
            setToast({ message: "充值成功", type: "success" });
          }
        })
        .catch(() => {});
    }
    fetchCredits();
    const timer = setInterval(fetchCredits, 2000); // 每 2 秒刷新积分
    return () => clearInterval(timer);
  }, [qrCodeUrl, initialCredits]);

  useEffect(() => {
    setLoading(true);
    API.getTransactions(page, 20)
      .then((data) => {
        setTransactions(data.transactions);
        setTotal(data.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, txRefreshTick]);

  const handleRecharge = async () => {
    const amount = parseFloat(rechargeAmount);
    if (!amount || amount < 0.01) {
      setToast({ message: "请输入正确的充值金额(最低 0.01 元)", type: "error" });
      return;
    }

    // 记录充值前的积分
    setInitialCredits(credits);
    setRecharging(true);
    try {
      const res = await API.createRecharge(amount);
      setQrCodeUrl(res.code_url);
    } catch (err) {
      setToast({
        message: err instanceof Error ? err.message : "充值失败",
        type: "error",
      });
    } finally {
      setRecharging(false);
    }
  };

  const formatTime = (time: string) => {
    const d = new Date(time);
    return d.toLocaleString("zh-CN");
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case "recharge":
        return "微信充值";
      case "consumption":
        return "消费";
      case "refund":
        return "退款";
      case "admin_adjustment":
        return "管理员调整";
      case "adjustment":
        return "积分调整";
      default:
        return type;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "recharge":
      case "admin_adjustment":
      case "adjustment":
        return "text-green-400";
      case "consumption":
        return "text-red-400";
      case "refund":
        return "text-yellow-400";
      default:
        return "text-text-2";
    }
  };

  return (
    <div className="min-h-screen bg-bg pb-20">
      <header className="sticky top-0 z-10 border-b border-hairline bg-bg/80 px-6 py-4 backdrop-blur-md">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setLocation("/app/projects")}
              className="flex items-center gap-2 text-text-3 transition-colors hover:text-text"
            >
              <ChevronLeft className="h-5 w-5" />
              <span>返回</span>
            </button>
          </div>
          <h1 className="text-lg font-medium">财务管理</h1>
          <div className="w-20" />
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-6 py-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="card">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-green-500/10 p-3">
                <Coins className="h-6 w-6 text-green-400" />
              </div>
              <div>
                <p className="text-sm text-text-3">当前积分</p>
                <p className="text-2xl font-semibold">{credits.toLocaleString()}</p>
                <p className="text-xs text-text-3">1 元 = 100 积分</p>
              </div>
            </div>
          </div>

          <button
            onClick={() => setShowRecharge(true)}
            className="card flex items-center gap-3 transition-all hover:border-accent/50"
          >
            <div className="rounded-lg bg-accent/10 p-3">
              <CreditCard className="h-6 w-6 text-accent" />
            </div>
            <div className="text-left">
              <p className="font-medium">微信充值</p>
              <p className="text-sm text-text-3">扫码支付即时到账</p>
            </div>
            <Plus className="ml-auto h-5 w-5 text-text-3" />
          </button>
        </div>

        <div className="card">
          <div className="mb-4 flex items-center gap-2">
            <History className="h-5 w-5 text-text-3" />
            <h2 className="font-medium">交易记录</h2>
            <span className="ml-auto text-sm text-text-3">共 {total} 条</span>
          </div>

          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 motion-safe:animate-spin text-accent" />
            </div>
          ) : transactions.length === 0 ? (
            <div className="py-8 text-center text-text-3">暂无交易记录</div>
          ) : (
            <div className="space-y-3">
              {transactions.map((tx) => (
                <div
                  key={tx.id}
                  className="flex items-center justify-between rounded-lg border border-hairline bg-bg-2 p-4"
                >
                  <div>
                    <p className="font-medium">
                      {tx.description || getTypeLabel(tx.type)}
                    </p>
                    <p className="mt-1 text-xs text-text-3">
                      {formatTime(tx.created_at)}
                    </p>
                    {tx.trade_no && (
                      <p className="mt-1 text-xs text-text-4">
                        订单号: {tx.trade_no}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p
                      className={`font-medium ${tx.amount >= 0 ? "text-green-400" : "text-red-400"}`}
                    >
                      {tx.amount >= 0 ? "+" : ""}
                      {tx.amount.toLocaleString()} 积分
                    </p>
                    <p className="mt-1 text-xs text-text-3">
                      余额: {tx.credits_after.toLocaleString()} 积分
                    </p>
                  </div>
                </div>
              ))}

              {/* 分页 */}
              {total > 20 && (
                <div className="mt-4 flex items-center justify-center gap-2">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page <= 1}
                    className="rounded-lg border border-hairline px-3 py-1.5 disabled:opacity-50"
                  >
                    上一页
                  </button>
                  <span className="text-sm text-text-3">
                    第 {page} / {Math.ceil(total / 20)} 页
                  </span>
                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={page >= Math.ceil(total / 20)}
                    className="rounded-lg border border-hairline px-3 py-1.5 disabled:opacity-50"
                  >
                    下一页
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {showRecharge && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-hairline bg-surface p-6 shadow-2xl">
            {!qrCodeUrl ? (
              <>
                <h3 className="mb-4 text-lg font-medium">微信充值</h3>
                <div className="mb-4">
                  <label className="mb-2 block text-sm text-text-3">
                    充值金额(元)
                  </label>
                  <input
                    type="number"
                    value={rechargeAmount}
                    onChange={(e) => setRechargeAmount(e.target.value)}
                    placeholder="请输入金额"
                    className="input-field w-full"
                    min="0.01"
                    step="0.01"
                  />
                  <p className="mt-1 text-xs text-text-3">1 元 = 100 积分</p>
                </div>
                <div className="flex gap-3">
                  {[10, 50, 100, 500].map((v) => (
                    <button
                      key={v}
                      onClick={() => setRechargeAmount(String(v))}
                      className="flex-1 rounded-lg border border-hairline bg-bg-2 py-2 text-center transition-colors hover:border-accent/50"
                    >
                      ¥{v}
                    </button>
                  ))}
                </div>
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={() => {
                      setShowRecharge(false);
                      setTxRefreshTick((x) => x + 1);  // 触发交易记录刷新
                      setQrCodeUrl(null);
                      setRechargeAmount("");
                    }}
                    className="flex-1 rounded-lg border border-hairline py-3 transition-colors hover:bg-bg-2"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleRecharge}
                    disabled={recharging || !rechargeAmount}
                    className="btn-primary flex flex-1 items-center justify-center gap-2"
                  >
                    {recharging ? (
                      <Loader2 className="h-4 w-4 motion-safe:animate-spin" />
                    ) : (
                      <QrCode className="h-4 w-4" />
                    )}
                    {recharging ? "生成中..." : "生成支付码"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-medium">扫码支付</h3>
                  <button
                    onClick={() => {
                      setQrCodeUrl(null);
                      setRechargeAmount("");
                      setShowRecharge(false);
                      setTxRefreshTick((x) => x + 1);  // 触发交易记录刷新
                    }}
                    className="text-text-3 hover:text-text"
                  >
                    ✕
                  </button>
                </div>
                <div className="flex flex-col items-center">
                  <div className="mb-4 rounded-lg border-2 border-dashed border-accent/30 bg-white p-4">
                    <QRCodeSVG
                      value={qrCodeUrl || ""}
                      size={160}
                      level="M"
                      includeMargin={true}
                    />
                  </div>
                  <p className="text-sm text-text-3">请使用微信扫码支付</p>
                  <p className="mt-2 text-lg font-medium">¥{rechargeAmount}</p>
                </div>
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={() => {
                      setQrCodeUrl(null);
                      setRechargeAmount("");
                      setShowRecharge(false);
                      setTxRefreshTick((x) => x + 1);  // 触发交易记录刷新
                    }}
                    className="flex-1 rounded-lg border border-hairline py-3 transition-colors hover:bg-bg-2"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => {
                      setQrCodeUrl(null);
                      setRechargeAmount("");
                      setShowRecharge(false);
                      setTxRefreshTick((x) => x + 1);  // 触发交易记录刷新
                    }}
                    className="btn-primary flex-1"
                  >
                    完成支付
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 transform rounded-lg border px-4 py-3 shadow-lg"
          style={{
            backgroundColor: "var(--color-surface)",
            borderColor:
              toast.type === "success"
                ? "var(--color-success)"
                : "var(--color-danger)",
          }}
        >
          <div className="flex items-center gap-2">
            {toast.type === "success" ? (
              <CheckCircle className="h-5 w-5 text-green-400" />
            ) : (
              <XCircle className="h-5 w-5 text-red-400" />
            )}
            <span style={{ color: "var(--color-text)" }}>{toast.message}</span>
          </div>
        </div>
      )}
    </div>
  );
}
