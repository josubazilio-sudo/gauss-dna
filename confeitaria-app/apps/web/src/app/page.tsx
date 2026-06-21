import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen">
      <header className="bg-pink-600 text-white p-6 shadow-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <h1 className="text-3xl font-bold tracking-tight">Confeitaria</h1>
          <nav className="flex gap-6 text-sm font-medium">
            <Link href="/" className="hover:text-pink-200">Início</Link>
            <Link href="/catalogo" className="hover:text-pink-200">Catálogo</Link>
            <Link href="/agenda" className="hover:text-pink-200">Agenda</Link>
            <Link href="/social" className="hover:text-pink-200">Social</Link>
            <Link href="/carrinho" className="hover:text-pink-200">Carrinho</Link>
          </nav>
        </div>
      </header>

      <section className="max-w-6xl mx-auto px-4 py-16 text-center">
        <h2 className="text-5xl font-bold mb-4">Bolos artesanais<br />com amor e tradição</h2>
        <p className="text-lg text-stone-600 mb-8 max-w-xl mx-auto">
          Encomende bolos personalizados, doces finos e muito mais.
          Entrega em toda a cidade.
        </p>
        <div className="flex gap-4 justify-center">
          <Link href="/catalogo" className="bg-pink-600 text-white px-8 py-3 rounded-full font-medium hover:bg-pink-700 transition">
            Ver Catálogo
          </Link>
          <Link href="/agenda" className="border-2 border-pink-600 text-pink-600 px-8 py-3 rounded-full font-medium hover:bg-pink-50 transition">
            Agendar Bolo
          </Link>
        </div>
      </section>

      <section className="bg-white py-16">
        <div className="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { icon: "🎂", title: "Bolos Personalizados", desc: "Do jeito que você sonhou" },
            { icon: "🧁", title: "Doces Finos", desc: "Para todas as ocasiões" },
            { icon: "🚚", title: "Delivery", desc: "Entregamos em sua casa" },
          ].map((item) => (
            <div key={item.title} className="text-center p-6 rounded-2xl bg-amber-50">
              <div className="text-4xl mb-3">{item.icon}</div>
              <h3 className="text-xl font-semibold mb-2">{item.title}</h3>
              <p className="text-stone-500">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="bg-stone-800 text-stone-400 text-center p-6 text-sm">
        &copy; 2026 Confeitaria. Todos os direitos reservados.
      </footer>
    </main>
  );
}
