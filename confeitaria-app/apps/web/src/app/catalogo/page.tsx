import Link from "next/link";

const produtos = [
  { id: 1, nome: "Bolo de Chocolate", preco: 89.90, img: "🍫", categoria: "Bolos" },
  { id: 2, nome: "Bolo de Morango", preco: 94.90, img: "🍓", categoria: "Bolos" },
  { id: 3, nome: "Bolo de Cenoura", preco: 79.90, img: "🥕", categoria: "Bolos" },
  { id: 4, nome: "Bolo de Limão", preco: 84.90, img: "🍋", categoria: "Bolos" },
  { id: 5, nome: "Brigadeiro (unid)", preco: 3.50, img: "🍫", categoria: "Doces" },
  { id: 6, nome: "Cupcake", preco: 8.90, img: "🧁", categoria: "Doces" },
  { id: 7, nome: "Torta de Morango", preco: 69.90, img: "🍰", categoria: "Tortas" },
  { id: 8, nome: "Torta de Limão", preco: 64.90, img: "🍋", categoria: "Tortas" },
];

export default function Catalogo() {
  return (
    <main className="min-h-screen">
      <header className="bg-pink-600 text-white p-6 shadow-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold">Confeitaria</Link>
          <nav className="flex gap-6 text-sm font-medium">
            <Link href="/" className="hover:text-pink-200">Início</Link>
            <Link href="/catalogo" className="text-pink-200">Catálogo</Link>
            <Link href="/carrinho" className="hover:text-pink-200">Carrinho</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Catálogo</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {produtos.map((p) => (
            <div key={p.id} className="bg-white rounded-2xl shadow-sm p-4 hover:shadow-md transition">
              <div className="text-5xl text-center mb-3">{p.img}</div>
              <span className="text-xs bg-pink-100 text-pink-700 px-2 py-1 rounded-full">{p.categoria}</span>
              <h3 className="font-semibold mt-2 text-lg">{p.nome}</h3>
              <p className="text-pink-600 font-bold text-xl mt-1">R$ {p.preco.toFixed(2)}</p>
              <button className="mt-3 w-full bg-pink-600 text-white py-2 rounded-full text-sm font-medium hover:bg-pink-700 transition">
                Adicionar ao Carrinho
              </button>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
