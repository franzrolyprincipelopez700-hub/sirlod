const localApi = import.meta.env.VITE_API_BASE_URL;
const developmentApi = import.meta.env.DEV ? import.meta.env.VITE_DEV_API_SERVER_URL : undefined;

export const SERVER_API_BASE_URL = process.env.API_SERVER_URL
  || developmentApi
  || (localApi?.startsWith("http://") || localApi?.startsWith("https://") ? localApi : "http://localhost:3000/api");
