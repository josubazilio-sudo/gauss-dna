import Image from "next/image";
import Link from "next/link";

export default function Header() {
  return (
    <header className="bg-pink-600 text-white p-4 shadow-md">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <div className="relative w-10 h-10 rounded-full overflow-hidden border-2 border-white">
            <Image
              src="/logo/logo-norminha.jpeg"
              alt="Norminha Bolos"
              fill
              className="object-cover"
              sizes="40px"
            />
          </div>
          <span className="text-xl font-bold">Norminha Bolos</span>
        </Link>
        <nav className="flex gap-6 text-sm font-medium">
          <Link href="/" className="hover:text-pink-200">Início</Link>
          <Link href="/catalogo" className="hover:text-pink-200">Catálogo</Link>
          <Link href="/agenda" className="hover:text-pink-200">Agenda</Link>
          <Link href="/social" className="hover:text-pink-200">Social</Link>
          <Link href="/carrinho" className="hover:text-pink-200">Carrinho</Link>
        </nav>
      </div>
    </header>
  );
}