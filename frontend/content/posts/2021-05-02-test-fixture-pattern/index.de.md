---
title: "Kontext zwischen Tests mit Fixtures teilen"
date: 2021-05-02T00:00:00+02:00
draft: false
author: "Marcel"
description: "Stell dir vor, du willst Mittag essen. Auf dem Tisch steht noch der schmutzige Frühstücksteller. Du hast drei Möglichkeiten: einen neuen Teller nehmen, den alten Teller abwaschen oder einfach vom schmutzigen Teller essen. Genau diese Regeln gelten auch für Tests."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

## Test Fixtures

Stell dir vor, du willst Mittag essen. Auf dem Tisch steht noch der schmutzige Frühstücksteller.  
Du hast drei Möglichkeiten: Du nimmst einen neuen Teller, du wäschst den alten Teller ab, oder du isst einfach vom schmutzigen Teller.  
Das war’s: Neuer Teller, sauberer Teller, schmutziger Teller.  
Genau die gleichen Regeln gelten auch für Tests.

### Transiente Fresh Fixture

Einen neuen Teller zu nehmen, nennt Meszaros im Buch *XUnit Test Patterns* eine **Transient Fresh Fixture**.  
Die Fixture wird zu Beginn jedes Tests von Grund auf neu erstellt.

Nehmen wir an, wir haben die folgende Testklasse:

```csharp
public class FreshFixtureTests
{
    [Fact]
    public void TestOne()
    {
        Debug.WriteLine("Execute Test 1");
        var stack = new Stack<int>();

        var count = stack.Count;
        Assert.Equal(0, count);
    }

    [Fact]
    public void TestTwo()
    {
        Debug.WriteLine("Execute Test 2");
        var stack = new Stack<int>();

        stack.Push(42);

        var count = stack.Count;
        Assert.Equal(1, count);
    }
}
```

Beide Tests teilen sich das gleiche Grund-Setup:

```csharp
var stack = new Stack<int>();
```

Eine transiente Fresh Fixture ist in Xunit leicht darzustellen, da Xunit genau diesen Ansatz fördert.  
Den gemeinsamen Code kannst du in den Konstruktor der Testklasse auslagern:

```csharp
public class FreshFixtureTests
{
    Stack<int> stack;

    public FreshFixtureTests()
    {
        Debug.WriteLine("Initialize Fixture");
        stack = new Stack<int>();
    }

    //...
}
```

Führen wir die Tests aus, sieht das so aus:

```
Initialize Fixture
Execute Test 1
Initialize Fixture
Execute Test 2
```

Wir sehen: Der Konstruktor der `FreshFixtureTests` wird vor jeder Testmethode ausgeführt.  
Das bedeutet, dass jede Testmethode in einer komplett neuen Instanz der Testklasse läuft.  

Dies ist eine klassische transiente Fresh Fixture. **Transient**, weil ihre Lebensdauer auf einen einzelnen Test beschränkt ist.  
**Fresh**, weil sie vor jedem Test neu initialisiert wird.  
Das sorgt dafür, dass Tests nicht miteinander kommunizieren können und daher in beliebiger Reihenfolge ausgeführt werden können.

Aber was passiert, wenn ein Teil deiner Test Fixture **nicht transient** ist?  
Das bedeutet, es gibt etwas Persistentes, das nach dem Test zurückgesetzt werden muss.

### Persistente Fresh Fixture

Meszaros nennt diese Art von Fixture **Persistent-Fresh**.  
Das ist der Frühstücksteller, den wir vor dem Mittagessen abwaschen.

Schauen wir in den Code:

```csharp
public class FreshFixtureTests : IDisposable
{
    //...

    public void Dispose()
    {
        Debug.WriteLine("Dispose Fixture");
        stack = null;
    }

    //...
}
```

Beim Ausführen wird die `Dispose`-Funktion nach jedem Test aufgerufen:

```
Initialize Fixture
Execute Test 1
Dispose Fixture
Initialize Fixture
Execute Test 2
Dispose Fixture
```

Wenn du die Wahl hast, sind transiente Fresh Fixtures die bessere Lösung.

> Achtung: NUnit erstellt z. B. nicht für jeden Test eine neue Instanz der Testklasse.  
> Deine Fixtures sind dort persistent, und du musst selbst geeignete **Teardown-Funktionen** einbauen.

### Persistente Shared Fixture

Die letzte Variante ist die **Persistente Shared Fixture**.  
Wenn du z. B. nach jedem Test die Datenbankverbindung auf- und abbauen würdest, würden deine Tests ewig laufen.  
Datenbankverbindungen sind teuer. In solchen Fällen ist es besser, eine einzige Verbindung für die gesamte Test-Suite zu teilen.

In Xunit geht das mit `IClassFixture`:

```csharp
public class DatabaseFixture : IDisposable
{
    public DatabaseFixture()
    {
        Debug.WriteLine("Initialize Shared Fixture");
        // ... initialize data in the test database ...
    }

    public void Dispose()
    {
        Debug.WriteLine("Dispose Shared Fixture");
        // ... clean up test data from the database ...
    }
}
```

```csharp
public class DatabaseTests : IClassFixture<DatabaseFixture>
{
    DatabaseFixture fixture;

    public DatabaseTests(DatabaseFixture fixture)
    {
        this.fixture = fixture;
    }

    [Fact]
    public void Test1()
    {
        Debug.WriteLine("Execute Test 1");
    }

    [Fact]
    public void Test2()
    {
        Debug.WriteLine("Execute Test 2");
    }
}
```

Führen wir diesen Test aus, sieht das so aus:

```
Initialize Shared Fixture
Execute Test 2
Execute Test 1
Dispose Shared Fixture
```

Kombiniert man alle Fixture-Typen, ergibt sich:

```
Initialize Shared Fixture
Initialize Fixture
Execute Test 1
Dispose Fixture
Initialize Fixture
Execute Test 2
Dispose Fixture
Dispose Shared Fixture
```

**Merke:** Je frischer, desto besser – und **Transient ist top**.  

Mehr zu diesem Thema findest du [hier](http://xunitpatterns.com/Fresh%20Fixture.html) und [hier](https://xunit.net/docs/shared-context).
