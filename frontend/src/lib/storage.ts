// Adaptador único de armazenamento local (auditoria v6, achado A-04).
//
// `localStorage` não é infalível: navegador em modo restrito, cota esgotada,
// bloqueio de cookies de terceiros num contexto embutido e modo privado de
// alguns navegadores fazem `getItem`/`setItem`/`removeItem` LANÇAREM, não
// devolverem vazio. O projeto acessava a API diretamente em 11 pontos, e o
// pior deles ficava em `main.tsx`, fora do `try` do bootstrap: uma exceção ali
// derrubava a aplicação antes do root renderizar, quando nem a tela de erro
// existe ainda. O usuário via página em branco.
//
// A regra que este módulo encerra: **persistência é melhoria progressiva**.
// Nada aqui é essencial para a sessão em curso — preferência de tema, usina
// selecionada e recorte de período são conveniências entre visitas. Falhar em
// gravá-las degrada a experiência; nunca deve impedir o app de abrir.
//
// Por isso a API devolve estado, não exceção: `get` devolve `null` (mesmo
// contrato de chave inexistente, que todo chamador já trata) e `set`/`remove`
// devolvem `false` para quem quiser saber se persistiu.

function warn(operation: string, key: string, error: unknown): void {
  // Silenciar por completo esconderia um navegador mal configurado de quem
  // depura; lançar quebraria o app. Registrar e seguir é o meio-termo.
  // eslint-disable-next-line no-console
  console.warn(`Armazenamento local indisponível (${operation} "${key}"):`, error)
}

export const safeStorage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key)
    } catch (error) {
      warn('leitura', key, error)
      return null
    }
  },

  set(key: string, value: string): boolean {
    try {
      window.localStorage.setItem(key, value)
      return true
    } catch (error) {
      warn('gravação', key, error)
      return false
    }
  },

  remove(key: string): boolean {
    try {
      window.localStorage.removeItem(key)
      return true
    } catch (error) {
      warn('remoção', key, error)
      return false
    }
  },
}
