import { redirect, type LoaderFunctionArgs } from "react-router";

export function loader({ request }: LoaderFunctionArgs) {
  return redirect(`/dashboard/anomalias${new URL(request.url).search}`);
}
