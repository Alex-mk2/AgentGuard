// Manifiesto de ejemplo para el botón «Ejemplo»: un agente de correo con la tríada completa (MCP).

export const EJEMPLO_TRIADA = {
  tools: [
    {
      name: "read_inbox",
      description: "Lists the latest emails in the user's inbox",
      inputSchema: { type: "object", properties: { folder: { type: "string" } } },
    },
    {
      name: "search_customers",
      description: "Finds customers in the CRM",
      inputSchema: { type: "object", properties: { name: { type: "string" } } },
    },
    {
      name: "fetch",
      description: "Fetches a URL from the internet and returns its content",
      inputSchema: { type: "object", properties: { url: { type: "string" } } },
    },
  ],
};
