import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-12">
      <Link href="/" className="mb-8 flex items-center gap-2">
        <span className="text-2xl font-extrabold tracking-tight">Cadence</span>
        <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
      </Link>
      <div className="w-full max-w-sm">{children}</div>
      <p className="mt-8 text-xs text-white/30">Studio-grade short-form, from one raw take.</p>
    </main>
  );
}
