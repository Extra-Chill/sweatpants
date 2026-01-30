"""Hello World - Example Sweatpants module."""

import asyncio

from sweatpants import Module


class HelloWorld(Module):
    """Simple example module demonstrating the Sweatpants SDK."""

    async def run(self, inputs, settings):
        """Greet the user multiple times."""
        name = inputs["name"]
        count = inputs.get("count", 3)

        await self.log(f"Starting to greet {name} {count} times")

        for i in range(count):
            if self.is_cancelled:
                await self.log("Job was cancelled")
                return

            await self.log(f"Greeting {i + 1} of {count}")

            await asyncio.sleep(1)

            yield {"greeting": f"Hello, {name}!", "iteration": i + 1}

            await self.save_checkpoint(completed=i + 1)

        await self.log("All greetings complete!")
