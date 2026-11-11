// Portao de lint MINIMO: so as duas regras de hooks do React (dependencias
// erradas de useEffect geram dado velho na tela e lacos de requisicao). Sem
// presets de estilo de proposito: o objetivo e pegar bug, nao formatar codigo.
//
// O parser e o do Babel, nao o typescript-eslint: o projeto usa TypeScript 7
// (compilador nativo, sem a API JS de que o typescript-eslint depende; o peer
// dele ainda exige <6.1). O Babel so le a sintaxe; o tipo continua a cargo do
// `npm run type-check`.
import babelParser from "@babel/eslint-parser";
import reactHooks from "eslint-plugin-react-hooks";

const regrasDeHooks = {
  "react-hooks/rules-of-hooks": "error",
  "react-hooks/exhaustive-deps": "error",
};

const parserPara = (isTSX) => ({
  parser: babelParser,
  parserOptions: {
    requireConfigFile: false,
    sourceType: "module",
    babelOptions: {
      configFile: false,
      babelrc: false,
      // So sintaxe (o parser nao transforma nada). "jsx" so no .tsx: em .ts o
      // "<T>(x)" e generico, nao JSX.
      parserOpts: { plugins: isTSX ? ["typescript", "jsx"] : ["typescript"] },
    },
  },
});

export default [
  { ignores: ["dist/**", "node_modules/**", "e2e/**", "playwright*.ts", "*.config.ts"] },
  {
    files: ["src/**/*.ts"],
    languageOptions: parserPara(false),
    plugins: { "react-hooks": reactHooks },
    rules: regrasDeHooks,
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
  {
    files: ["src/**/*.tsx"],
    languageOptions: parserPara(true),
    plugins: { "react-hooks": reactHooks },
    rules: regrasDeHooks,
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
];
