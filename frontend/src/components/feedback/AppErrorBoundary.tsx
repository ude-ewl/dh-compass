import { Component, type ErrorInfo, type ReactNode } from "react";

import { FailureState } from "./StateViews";

type Props = { children: ReactNode };
type State = { error: Error | null };

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      "Unhandled frontend rendering error",
      error,
      info.componentStack,
    );
  }

  render() {
    if (this.state.error) {
      return <FailureState error={this.state.error} />;
    }
    return this.props.children;
  }
}
